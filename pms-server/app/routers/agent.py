import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import create_agent_token, decode_token, hash_password
from app.core.redis import get_redis, endpoint_online_key, enrollment_token_key
from app.core.deps import get_current_agent, get_current_user, require_role
from app.core.exceptions import UnauthorizedError, BadRequestError, NotFoundError
from app.core.security import generate_enrollment_token
from app.models.endpoint import Endpoint
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.agent import (
    AgentEnrollRequest, AgentEnrollResponse,
    HeartbeatRequest, HeartbeatResponse,
    AgentTask, TaskStatusRequest, InventoryRequest,
)
from app.schemas.endpoint import EnrollmentTokenRequest, EnrollmentTokenResponse
from app.core.ws import ws_manager
from app.config import settings

router = APIRouter(prefix="/agent", tags=["agent"])
admin_router = APIRouter(prefix="/agent-admin", tags=["agent-admin"])


class AgentUpgradeRequest(BaseModel):
    target: str = "all"  # "all" | endpoint_id
    version: str
    download_url: str
    file_hash_sha256: str
    file_size_bytes: int | None = None


@admin_router.post("/enrollment-tokens", response_model=EnrollmentTokenResponse)
async def create_enrollment_token(
    body: EnrollmentTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin", "operator")),
):
    token = generate_enrollment_token()
    expire_seconds = body.expires_hours * 3600
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_hours)

    redis = await get_redis()
    await redis.setex(
        enrollment_token_key(token),
        expire_seconds,
        body.organization_id or "",
    )

    db.add(AuditLog(
        actor_type="user",
        actor_id=current_user.id,
        action="agent.enrollment_token.create",
        detail={"label": body.label, "expires_hours": body.expires_hours},
    ))
    await db.commit()

    return EnrollmentTokenResponse(token=token, expires_at=expires_at)


@router.post("/enroll", response_model=AgentEnrollResponse)
async def enroll(
    body: AgentEnrollRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    key = enrollment_token_key(body.enrollment_token)
    org_id = await redis.get(key)

    if org_id is None:
        raise UnauthorizedError("Invalid or expired enrollment token")

    # Consume the enrollment token (one-time use)
    await redis.delete(key)

    endpoint_id = str(uuid.uuid4())
    agent_token = create_agent_token(endpoint_id, body.hostname, body.platform)

    endpoint = Endpoint(
        id=endpoint_id,
        hostname=body.hostname,
        fqdn=body.fqdn,
        ip_address=body.ip_address or (request.client.host if request.client else None),
        mac_address=body.mac_address,
        platform=body.platform,
        os_name=body.os_name,
        os_version=body.os_version,
        os_build=body.os_build,
        arch=body.arch,
        agent_version=body.agent_version,
        agent_token=agent_token,
        organization_id=org_id if org_id else None,
        status="active",
        enrolled_at=datetime.now(timezone.utc),
    )
    db.add(endpoint)
    db.add(AuditLog(
        actor_type="agent",
        actor_id=endpoint_id,
        action="agent.enroll",
        resource="endpoint",
        resource_id=endpoint_id,
        detail={"hostname": body.hostname, "platform": body.platform},
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()

    # Mark as online immediately
    await redis.setex(
        endpoint_online_key(endpoint_id),
        settings.agent_offline_threshold_seconds,
        "1",
    )

    # 서명 검증용 공개키 포함 (에이전트가 로컬에 저장)
    server_public_key = None
    try:
        from app.core.signing import get_public_key_pem
        import os
        if os.path.exists(settings.jwt_public_key_path):
            server_public_key = get_public_key_pem(settings.jwt_public_key_path)
    except Exception:
        pass

    return AgentEnrollResponse(
        agent_token=agent_token,
        endpoint_id=endpoint_id,
        server_time=datetime.now(timezone.utc),
        server_public_key=server_public_key,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    body: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    endpoint: Endpoint = Depends(get_current_agent),
):
    now = datetime.now(timezone.utc)

    # Update last_seen and refresh online TTL
    endpoint.last_seen_at = now
    if body.agent_version:
        endpoint.agent_version = body.agent_version
    db.add(endpoint)

    redis = await get_redis()
    await redis.setex(
        endpoint_online_key(endpoint.id),
        settings.agent_offline_threshold_seconds,
        "1",
    )

    await db.commit()

    # Check if there are pending tasks for this endpoint
    task_key = f"pms:tasks:{endpoint.id}"
    has_tasks = await redis.llen(task_key) > 0

    # Push real-time status update to all connected dashboard clients
    if ws_manager.connection_count > 0:
        await ws_manager.broadcast({
            "type": "endpoint_status_change",
            "endpoint_id": endpoint.id,
            "hostname": endpoint.hostname,
            "is_online": True,
            "last_seen_at": now.isoformat(),
            "agent_version": endpoint.agent_version,
        })

    return HeartbeatResponse(
        server_time=now,
        config_version=1,
        has_pending_tasks=has_tasks,
        next_inventory_due=None,
    )


@router.get("/tasks", response_model=list[AgentTask])
async def get_tasks(
    endpoint: Endpoint = Depends(get_current_agent),
):
    redis = await get_redis()
    task_key = f"pms:tasks:{endpoint.id}"

    # Return up to 5 pending tasks (LRANGE is non-destructive)
    import json
    raw_tasks = await redis.lrange(task_key, 0, 4)
    tasks = []
    for raw in raw_tasks:
        try:
            tasks.append(AgentTask.model_validate(json.loads(raw)))
        except Exception:
            continue

    return tasks


@router.post("/tasks/{task_id}/status")
async def update_task_status(
    task_id: str,
    body: TaskStatusRequest,
    db: AsyncSession = Depends(get_db),
    endpoint: Endpoint = Depends(get_current_agent),
):
    import json
    from app.models.deployment import DeploymentResult, Deployment

    now = datetime.now(timezone.utc)
    terminal = body.status in ("success", "failed", "rolled_back", "skipped")

    # 완료/실패 시 에이전트 큐에서 제거
    if terminal:
        redis = await get_redis()
        task_key = f"pms:tasks:{endpoint.id}"
        raw_tasks = await redis.lrange(task_key, 0, -1)
        for raw in raw_tasks:
            try:
                if json.loads(raw).get("task_id") == task_id:
                    await redis.lrem(task_key, 1, raw)
                    break
            except Exception:
                continue

    # DeploymentResult 갱신 (task_id == DeploymentResult.id)
    dr_result = await db.execute(
        select(DeploymentResult).where(DeploymentResult.id == task_id)
    )
    dr = dr_result.scalar_one_or_none()
    if dr:
        dr.status = body.status
        dr.error_message = body.error_message
        dr.exit_code = body.exit_code
        if body.rollback_snapshot_id:
            dr.rollback_snapshot_id = body.rollback_snapshot_id
        if body.status == "downloading":
            dr.download_started_at = now
        elif body.status == "installing":
            dr.install_started_at = now
        elif terminal:
            dr.completed_at = now
        db.add(dr)

        # 실시간 배포 진행 상황 브로드캐스트
        if ws_manager.connection_count > 0:
            await ws_manager.broadcast({
                "type": "deployment_progress",
                "deployment_id": dr.deployment_id,
                "endpoint_id": endpoint.id,
                "hostname": endpoint.hostname,
                "status": body.status,
                "error_message": body.error_message,
            })

        # 배포 완료 여부 확인 (비동기 Celery 태스크로 위임)
        if terminal:
            from app.tasks.deployment_tasks import finalize_deployment
            finalize_deployment.apply_async(args=[dr.deployment_id], countdown=5)

    db.add(AuditLog(
        actor_type="agent",
        actor_id=endpoint.id,
        action=f"task.{body.status}",
        resource="task",
        detail={"task_id": task_id, "status": body.status, "exit_code": body.exit_code},
    ))
    await db.commit()

    return {"task_id": task_id, "status": body.status}


@router.post("/inventory")
async def submit_inventory(
    body: InventoryRequest,
    db: AsyncSession = Depends(get_db),
    endpoint: Endpoint = Depends(get_current_agent),
):
    from app.models.software import EndpointSoftware
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = body.collected_at

    # Upsert each software item: update version/vendor if raw_name already exists
    for item in body.software:
        stmt = pg_insert(EndpointSoftware).values(
            id=str(uuid.uuid4()),
            endpoint_id=endpoint.id,
            raw_name=item.raw_name,
            version=item.version,
            install_path=item.install_path,
            vendor=item.vendor,
            detected_at=now,
        ).on_conflict_do_update(
            constraint="uq_endpoint_software",
            set_={
                "version": item.version,
                "install_path": item.install_path,
                "vendor": item.vendor,
                "detected_at": now,
            },
        )
        await db.execute(stmt)

    db.add(AuditLog(
        actor_type="agent",
        actor_id=endpoint.id,
        action="agent.inventory.submit",
        resource="endpoint",
        resource_id=endpoint.id,
        detail={"software_count": len(body.software), "collected_at": now.isoformat()},
    ))
    await db.commit()
    return {"received": len(body.software)}


@admin_router.post("/upgrade")
async def push_agent_upgrade(
    body: AgentUpgradeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin")),
):
    """선택한 엔드포인트(또는 전체)에 에이전트 자동 업그레이드 태스크를 큐에 삽입합니다."""
    from app.models.endpoint import Endpoint
    from sqlalchemy import select

    redis = await get_redis()
    now = datetime.now(timezone.utc)

    if body.target == "all":
        result = await db.execute(select(Endpoint).where(Endpoint.status == "active"))
        endpoints = result.scalars().all()
        target_ids = [ep.id for ep in endpoints]
    else:
        result = await db.execute(select(Endpoint).where(Endpoint.id == body.target))
        ep = result.scalar_one_or_none()
        if not ep:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Endpoint not found")
        target_ids = [ep.id]

    task_template = {
        "task_type": "agent_upgrade",
        "priority": 10,
        "created_at": now.isoformat(),
        "deadline": None,
        "payload": {
            "version": body.version,
            "download_url": body.download_url,
            "file_hash_sha256": body.file_hash_sha256,
            "file_size_bytes": body.file_size_bytes,
        },
    }

    queued = 0
    for ep_id in target_ids:
        task = {**task_template, "task_id": str(uuid.uuid4())}
        await redis.rpush(f"pms:tasks:{ep_id}", __import__("json").dumps(task))
        await redis.expire(f"pms:tasks:{ep_id}", 172800)
        queued += 1

    db.add(AuditLog(
        actor_type="user",
        actor_id=current_user.id,
        action="agent.upgrade.push",
        detail={"version": body.version, "target": body.target, "queued": queued},
    ))
    await db.commit()

    return {"version": body.version, "queued": queued}
