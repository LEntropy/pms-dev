import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError, BadRequestError
from app.core.ws import ws_manager
from app.models.deployment import Deployment, DeploymentResult
from app.models.patch import Patch
from app.models.user import User
from app.schemas.policy import (
    DeploymentCreateRequest, DeploymentResponse, DeploymentResultResponse,
)

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.get("", response_model=list[DeploymentResponse])
async def list_deployments(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Deployment)
    if status:
        q = q.where(Deployment.status == status)
    q = q.order_by(Deployment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    return [DeploymentResponse.model_validate(d) for d in result.scalars()]


@router.post("", response_model=DeploymentResponse, status_code=201)
async def create_deployment(
    body: DeploymentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin", "operator")),
):
    # 패치 존재 및 활성 여부 확인
    pat_res = await db.execute(select(Patch).where(Patch.id == body.patch_id, Patch.is_active == True))
    if not pat_res.scalar_one_or_none():
        raise NotFoundError("Patch not found or inactive")

    deployment = Deployment(
        id=str(uuid.uuid4()),
        patch_id=body.patch_id,
        policy_id=body.policy_id,
        initiated_by=current_user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        scheduled_at=body.scheduled_at,
        status="pending",
        success_count=0,
        failure_count=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    # Celery 태스크 실행 (즉시 또는 스케줄 시간에)
    from app.tasks.deployment_tasks import schedule_deployment
    if body.scheduled_at:
        eta = body.scheduled_at
        schedule_deployment.apply_async(args=[deployment.id], eta=eta)
    else:
        schedule_deployment.delay(deployment.id)

    return DeploymentResponse.model_validate(deployment)


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    dep = result.scalar_one_or_none()
    if not dep:
        raise NotFoundError("Deployment not found")
    return DeploymentResponse.model_validate(dep)


@router.get("/{deployment_id}/results", response_model=list[DeploymentResultResponse])
async def get_results(
    deployment_id: str,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(DeploymentResult).where(DeploymentResult.deployment_id == deployment_id)
    if status:
        q = q.where(DeploymentResult.status == status)
    result = await db.execute(q.order_by(DeploymentResult.status))
    return [DeploymentResultResponse.model_validate(r) for r in result.scalars()]


@router.post("/{deployment_id}/cancel")
async def cancel_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin", "operator")),
):
    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    dep = result.scalar_one_or_none()
    if not dep:
        raise NotFoundError("Deployment not found")
    if dep.status not in ("pending", "in_progress"):
        raise BadRequestError(f"Cannot cancel deployment in status '{dep.status}'")

    dep.status = "cancelled"
    dep.completed_at = datetime.now(timezone.utc)
    db.add(dep)

    # 아직 pending인 결과 행을 skipped로 처리
    pending_res = await db.execute(
        select(DeploymentResult).where(
            DeploymentResult.deployment_id == deployment_id,
            DeploymentResult.status == "pending",
        )
    )
    for dr in pending_res.scalars():
        dr.status = "skipped"
        db.add(dr)

    await db.commit()
    return {"id": deployment_id, "status": "cancelled"}


@router.post("/{deployment_id}/rollback")
async def rollback_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    """실패한 엔드포인트에 롤백 태스크를 큐에 삽입합니다."""
    import json
    from app.core.redis import get_redis

    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    dep = result.scalar_one_or_none()
    if not dep:
        raise NotFoundError("Deployment not found")

    failed_res = await db.execute(
        select(DeploymentResult).where(
            DeploymentResult.deployment_id == deployment_id,
            DeploymentResult.status == "failed",
            DeploymentResult.rollback_snapshot_id != None,
        )
    )
    redis = await get_redis()
    rollback_count = 0

    for dr in failed_res.scalars():
        rollback_task = {
            "task_id": str(uuid.uuid4()),
            "task_type": "patch_rollback",
            "priority": 10,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deadline": None,
            "payload": {"rollback_snapshot_id": dr.rollback_snapshot_id},
        }
        await redis.rpush(f"pms:tasks:{dr.endpoint_id}", json.dumps(rollback_task))
        rollback_count += 1

    dep.status = "rolled_back"
    db.add(dep)
    await db.commit()

    return {"deployment_id": deployment_id, "rollback_queued": rollback_count}


@router.get("/stats/summary")
async def deployment_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Deployment.status, func.count().label("count"))
        .group_by(Deployment.status)
    )
    return {"by_status": {row.status: row.count for row in result}}
