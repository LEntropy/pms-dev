# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Self-hosted **Patch Management System (PMS)** — centralised patch orchestration for Windows/Linux endpoints. Three sub-projects:

| Directory | Stack | Role |
|---|---|---|
| `pms-server/` | Python 3.11, FastAPI, SQLAlchemy 2 async | REST API + WebSocket server |
| `pms-agent/` | Python 3.11, httpx | Cross-platform endpoint daemon |
| `pms-dashboard/` | Vue 3, TypeScript, Vite | Admin SPA |
| `infra/` | Docker Compose, Nginx | Local dev + prod infra |

---

## Commands

### Server (run from `pms-server/`)

```bash
# Install deps
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Dev server (requires running Postgres/Redis)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# DB migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic current

# Seed initial admin + enrollment token
python seed.py

# Celery worker
celery -A app.tasks.celery_app worker --loglevel=info -Q default,deployment,reporting -c 2

# Celery beat (scheduled tasks)
celery -A app.tasks.celery_app beat --loglevel=info

# Run all tests (no real DB/Redis needed)
pytest tests/ -v

# Run a single test file
pytest tests/test_compliance.py -v

# Run a single test by name
pytest tests/test_security.py::TestJWT::test_decode_valid_token -v

# Coverage
pytest tests/ --cov=app --cov-report=term-missing
```

### Dashboard (run from `pms-dashboard/`)

```bash
npm install
npm run dev      # http://localhost:5173 — proxies /api and /ws to localhost:8000
npm run build
```

### Docker (run from `infra/`)

```bash
docker compose up -d              # start all services
docker compose logs -f pms-server # watch server logs
docker compose ps                 # check health status
docker exec pms-server python seed.py
docker compose down -v            # full reset including volumes
```

---

## Architecture

### Request Flow

```
Client → Nginx(:80) → FastAPI(:8000)
                          │
              ┌───────────┼─────────────┐
           PostgreSQL   Redis         MinIO
              (ORM)   (TTL/queue)   (files)
                          │
                      Celery workers
```

### Auth — Two Token Types (JWT RS256)

Both tokens are verified by `decode_token()` in `app/core/security.py`. The `type` claim distinguishes them:

- **`type: access`** — 15-min user tokens. `get_current_user` dep in `app/core/deps.py` resolves to a `User` model.
- **`type: agent`** — 30-day endpoint tokens. `get_current_agent` dep resolves to an `Endpoint` model.

RBAC roles: `superadmin > admin > operator > viewer`. Use `require_role("admin", "operator")` as a FastAPI dependency.

RSA keys are auto-generated at startup (`app/core/security.py:generate_rsa_keys`) and stored in `keys/private.pem` / `keys/public.pem`. In tests, `_load_private_key()` reads `JWT_PRIVATE_KEY_PATH` from `os.environ` first (not from the cached `settings` object) — this is intentional to support monkeypatching.

### Agent Online Status

Online/offline state is tracked purely via **Redis TTL**, not the DB:
- Key: `pms:online:{endpoint_id}`, TTL = 900 s (3 missed heartbeats at 5-min intervals)
- Set/refreshed on: enrollment, heartbeat
- No TTL = offline

### Agent Task Queue (Pull Model)

Tasks are stored as JSON in a Redis list `pms:tasks:{endpoint_id}`:
- **Push**: `RPUSH` by `schedule_deployment` Celery task or `push_agent_upgrade`
- **Poll**: agent calls `GET /agent/tasks` → `LRANGE 0 4` (non-destructive)
- **Remove**: `LREM` on terminal status (`success | failed | rolled_back | skipped`)

Task objects carry `task_type`, `priority`, `payload` (download_url, sha256, bandwidth_limit_kbps, etc.).

### Deployment Pipeline

1. `POST /api/v1/deployments/` creates a `Deployment` row + fires `schedule_deployment.apply_async`
2. Celery `schedule_deployment` task: expands target group → creates one `DeploymentResult` per endpoint → pushes task JSON to each agent's Redis queue
3. Agent polls tasks, downloads via presigned MinIO URL, installs, calls `POST /agent/tasks/{id}/status`
4. On terminal status, `finalize_deployment.apply_async(countdown=5)` checks if all results are terminal and updates parent `Deployment.status`
5. WebSocket broadcasts `deployment_progress` events at each status change

### Celery Task Structure

Celery workers run synchronously but most app code is async. The `_run_async(coro)` helper in `deployment_tasks.py` creates a fresh event loop per invocation. Each Celery task re-creates its own SQLAlchemy engine + session (no shared connection pool).

Three queues:
- `deployment` — `schedule_deployment`, `finalize_deployment`
- `reporting` — `generate_compliance_report`
- `default` — `ldap_sync`, `openvas_scan`

### Compliance Engine (`app/services/compliance.py`)

Compares `EndpointSoftware.raw_name + version` against `SoftwareProduct` + `Patch` catalog rows. `compare_versions()` handles `None` inputs (returns `-1`/`0`), tries `packaging.version.Version` first then falls back to numeric tuple comparison.

### Policy Engine (`app/services/policy_engine.py`)

`resolve_policy(db, endpoint, patch)` returns the highest-priority matching `Policy`. Matching checks: target (endpoint_id or group membership), `patch_types`, exception lists, per-endpoint `PolicyException` rows. Lower `priority` integer = higher precedence.

### Database Models

All models extend `Base` from `app/database.py`. Key relationships:

```
Organization (tree)
  └─ Endpoint ──── EndpointGroupMember ──► EndpointGroup ◄── Policy.targets
       └─ EndpointSoftware (upsert on uq_endpoint_software)
       └─ DeploymentResult ──► Deployment ──► Patch
                                               └─ SoftwareProduct ──► SoftwareVendor
AuditLog (append-only, no FK constraints)
```

UUID primary keys stored as `VARCHAR` (not native UUID) — always `str` in Python.

### Testing Pattern

Tests do **not** need a real DB or Redis. `tests/conftest.py` sets env vars early (before `app.config.settings` is instantiated). API integration tests use FastAPI `dependency_overrides`:

```python
app.dependency_overrides[get_db]    = lambda: AsyncMock()   # async generator
app.dependency_overrides[get_redis] = lambda: AsyncMock()   # coroutine
```

The `rsa_keys` session fixture in `conftest.py` generates a real RSA key pair in a temp dir and returns `(private_path, public_path)`. Tests that need JWT signing must set `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` env vars via `monkeypatch.setenv` before importing `app.core.security`.

### Known Dependency Constraints

- `bcrypt==4.0.1` — **must not be upgraded to 5.x**. passlib 1.7.4 uses a >72-byte test password internally that bcrypt 5.x rejects.
- `cryptography==42.0.8` — `hashes.Prehashed` does not exist in this version; `signing.py` passes raw bytes to `.sign()` with `hashes.SHA256()`.

---

## Key Files by Concern

| Concern | File |
|---|---|
| App entry point + router registration | `pms-server/app/main.py` |
| All env-var config | `pms-server/app/config.py` |
| JWT + password hashing | `pms-server/app/core/security.py` |
| Auth dependencies (user / agent / RBAC) | `pms-server/app/core/deps.py` |
| Redis helpers + key naming | `pms-server/app/core/redis.py` |
| WebSocket broadcast manager | `pms-server/app/core/ws.py` |
| File signing (RSA-PKCS1v15-SHA256) | `pms-server/app/core/signing.py` |
| Agent communication contract | `pms-server/app/routers/agent.py` |
| Deployment Celery tasks | `pms-server/app/tasks/deployment_tasks.py` |
| Compliance calculation | `pms-server/app/services/compliance.py` |
| Policy resolution | `pms-server/app/services/policy_engine.py` |
| MinIO presigned URLs | `pms-server/app/services/file_distribution.py` |
| Agent HTTP client (retry + CA pin) | `pms-agent/agent/api_client.py` |
| Agent main loop | `pms-agent/agent/main.py` |
| Dashboard API proxy config | `pms-dashboard/vite.config.ts` |
