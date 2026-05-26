"""인증 API 통합 테스트 — FastAPI TestClient + dependency override."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(scope="module")
def app_client():
    """DB/Redis를 override한 TestClient."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db
    from app.core.redis import get_redis

    # DB dependency override
    async def _fake_db():
        yield AsyncMock()

    async def _fake_redis():
        return AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_redis] = _fake_redis

    with patch("app.core.redis.close_redis", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    app.dependency_overrides.clear()


class TestHealthCheck:
    def test_health_returns_200(self, app_client):
        resp = app_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_openapi_schema_accessible(self, app_client):
        resp = app_client.get("/api/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data


class TestAuthEndpoints:
    def test_login_missing_body_returns_422(self, app_client):
        resp = app_client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422

    def test_login_returns_json_error_not_crash(self, app_client):
        """잘못된 자격증명은 4xx를 반환해야 하며 500이 되어선 안 됨."""
        resp = app_client.post(
            "/api/v1/auth/login",
            json={"username": "nobody@example.com", "password": "wrong"},
        )
        assert resp.status_code in (401, 422, 404)
        assert resp.status_code < 500

    def test_protected_endpoints_require_auth(self, app_client):
        protected = [
            "/api/v1/endpoints/",
            "/api/v1/patches/",
            "/api/v1/policies/",
            "/api/v1/deployments/",
            "/api/v1/audit",
        ]
        for url in protected:
            resp = app_client.get(url)
            assert resp.status_code in (401, 403), f"{url} returned {resp.status_code}"

    def test_invalid_bearer_token_rejected(self, app_client):
        resp = app_client.get(
            "/api/v1/endpoints/",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert resp.status_code in (401, 403)

    def test_malformed_authorization_header(self, app_client):
        resp = app_client.get(
            "/api/v1/endpoints/",
            headers={"Authorization": "NotBearer tokenvalue"},
        )
        assert resp.status_code in (401, 403)


class TestAgentEnroll:
    def test_enroll_no_payload_returns_422(self, app_client):
        resp = app_client.post("/api/v1/agent/enroll", json={})
        assert resp.status_code == 422

    def test_enroll_invalid_token_rejected(self, app_client):
        resp = app_client.post(
            "/api/v1/agent/enroll",
            json={
                "enrollment_token": "bad-token-xyz",
                "hostname": "pc-test-001",
                "platform": "windows",
                "ip_address": "10.0.0.1",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "os_version": "Windows 10 22H2",
                "agent_version": "1.0.0",
            },
        )
        # Redis mock에서 토큰을 찾지 못해 401 반환
        assert resp.status_code in (401, 422, 500)
        assert resp.status_code != 200

    def test_heartbeat_requires_auth(self, app_client):
        resp = app_client.post("/api/v1/agent/heartbeat", json={"status": "online"})
        assert resp.status_code in (401, 403, 422)

    def test_tasks_poll_requires_auth(self, app_client):
        resp = app_client.get("/api/v1/agent/tasks")
        assert resp.status_code in (401, 403)


class TestPatchesEndpoint:
    def test_get_patches_requires_auth(self, app_client):
        resp = app_client.get("/api/v1/patches/")
        assert resp.status_code in (401, 403)

    def test_create_patch_requires_auth(self, app_client):
        resp = app_client.post("/api/v1/patches/", data={"title": "Test Patch"})
        assert resp.status_code in (401, 403, 422)


class TestDeploymentsEndpoint:
    def test_list_deployments_requires_auth(self, app_client):
        resp = app_client.get("/api/v1/deployments/")
        assert resp.status_code in (401, 403)

    def test_create_deployment_requires_auth(self, app_client):
        resp = app_client.post("/api/v1/deployments/", json={})
        assert resp.status_code in (401, 403, 422)
