"""
배포 Celery 태스크.
schedule_deployment: 배포 대상 확장 → 에이전트 Redis 큐에 태스크 삽입
update_deployment_result: 에이전트 보고를 받아 DeploymentResult 갱신 후 WebSocket broadcast
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from app.tasks.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Celery 워커(동기 환경)에서 async 코루틴을 실행합니다."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.deployment_tasks.schedule_deployment",
    queue="deployment",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def schedule_deployment(self, deployment_id: str):
    """
    배포 대상 엔드포인트를 확장하고 각 에이전트의 Redis 큐에 태스크를 삽입합니다.
    """
    try:
        _run_async(_do_schedule(deployment_id))
    except Exception as exc:
        logger.error("schedule_deployment failed for %s: %s", deployment_id, exc)
        self.retry(exc=exc)


async def _do_schedule(deployment_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from redis.asyncio import from_url

    from app.models.deployment import Deployment, DeploymentResult
    from app.models.patch import Patch
    from app.models.endpoint import Endpoint
    from app.services.policy_engine import expand_targets, is_within_install_window
    from app.services.file_distribution import get_presigned_download_url

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    redis = await from_url(settings.redis_url, decode_responses=True)

    async with Session() as db:
        dep_result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
        deployment = dep_result.scalar_one_or_none()
        if not deployment or deployment.status not in ("pending", "in_progress"):
            return

        patch_result = await db.execute(select(Patch).where(Patch.id == deployment.patch_id))
        patch = patch_result.scalar_one_or_none()
        if not patch:
            return

        # 정책 설치 윈도우 확인
        if deployment.policy_id:
            from app.models.policy import Policy
            pol_res = await db.execute(select(Policy).where(Policy.id == deployment.policy_id))
            policy = pol_res.scalar_one_or_none()
            if policy and not is_within_install_window(policy):
                logger.info("Deployment %s outside install window, rescheduling", deployment_id)
                # 1시간 후 재시도
                schedule_deployment.apply_async(args=[deployment_id], countdown=3600)
                return

        # 대상 엔드포인트 확장
        endpoint_ids = await expand_targets(db, deployment.target_type, deployment.target_id)
        if not endpoint_ids:
            deployment.status = "completed"
            db.add(deployment)
            await db.commit()
            return

        # 각 엔드포인트에 DeploymentResult 생성
        now = datetime.now(timezone.utc)
        deployment.status = "in_progress"
        deployment.started_at = now
        deployment.total_targets = len(endpoint_ids)
        db.add(deployment)

        download_url = get_presigned_download_url(patch.file_path)
        task_deadline = now + timedelta(hours=4)

        max_concurrent = 10
        if deployment.policy_id:
            from app.models.policy import Policy
            pol_res = await db.execute(select(Policy).where(Policy.id == deployment.policy_id))
            policy = pol_res.scalar_one_or_none()
            if policy:
                max_concurrent = policy.max_concurrent

        # 대역폭 제한 정책 적용
        bandwidth_kbps = None
        if deployment.policy_id:
            from app.models.policy import Policy
            pol_res = await db.execute(select(Policy).where(Policy.id == deployment.policy_id))
            policy = pol_res.scalar_one_or_none()
            if policy:
                bandwidth_kbps = policy.bandwidth_limit_kbps

        for i, ep_id in enumerate(endpoint_ids):
            result_row = DeploymentResult(
                id=str(uuid.uuid4()),
                deployment_id=deployment_id,
                endpoint_id=ep_id,
                status="pending",
            )
            db.add(result_row)

            # 동시 설치 제한: max_concurrent씩 묶어 다른 시간대에 분산
            delay_minutes = (i // max_concurrent) * 5
            scheduled_time = now + timedelta(minutes=delay_minutes)

            task_payload = {
                "task_id": result_row.id,
                "task_type": "patch_install",
                "priority": 50,
                "created_at": now.isoformat(),
                "deadline": task_deadline.isoformat(),
                "payload": {
                    "patch_id": patch.id,
                    "download_url": download_url,
                    "file_hash_sha256": patch.file_hash_sha256,
                    "file_size_bytes": patch.file_size_bytes,
                    "requires_reboot": patch.requires_reboot,
                    "bandwidth_limit_kbps": bandwidth_kbps,
                },
            }

            # Redis 에이전트 큐에 삽입 (RPUSH = 큐 뒤에 추가)
            await redis.rpush(f"pms:tasks:{ep_id}", json.dumps(task_payload))
            # 큐 항목은 48시간 후 자동 만료
            await redis.expire(f"pms:tasks:{ep_id}", 172800)

        await db.commit()
        logger.info("Deployment %s started: %d endpoints queued", deployment_id, len(endpoint_ids))

    await redis.aclose()
    await engine.dispose()


@celery_app.task(
    name="app.tasks.deployment_tasks.finalize_deployment",
    queue="deployment",
)
def finalize_deployment(deployment_id: str):
    """모든 결과가 들어온 후 Deployment 최종 상태를 계산합니다."""
    _run_async(_do_finalize(deployment_id))


async def _do_finalize(deployment_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select, func

    from app.models.deployment import Deployment, DeploymentResult

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        dep_res = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
        deployment = dep_res.scalar_one_or_none()
        if not deployment:
            return

        counts_res = await db.execute(
            select(DeploymentResult.status, func.count().label("n"))
            .where(DeploymentResult.deployment_id == deployment_id)
            .group_by(DeploymentResult.status)
        )
        counts = {row.status: row.n for row in counts_res}

        pending = counts.get("pending", 0) + counts.get("downloading", 0) + counts.get("installing", 0)
        if pending > 0:
            return  # 아직 진행 중

        deployment.success_count = counts.get("success", 0) + counts.get("rolled_back", 0)
        deployment.failure_count = counts.get("failed", 0)
        deployment.completed_at = datetime.now(timezone.utc)
        deployment.status = "completed" if deployment.failure_count == 0 else "failed"
        db.add(deployment)
        await db.commit()

        logger.info(
            "Deployment %s finalized: status=%s success=%d failure=%d",
            deployment_id, deployment.status, deployment.success_count, deployment.failure_count,
        )

        # 이메일 알림 발송 (initiated_by 사용자 이메일 조회)
        from app.services.notification import send_deployment_notification
        from app.models.user import User

        recipient = None
        if deployment.initiated_by:
            user_res = await db.execute(select(User).where(User.id == deployment.initiated_by))
            user = user_res.scalar_one_or_none()
            if user:
                recipient = user.email

        await send_deployment_notification(
            deployment_id=deployment_id,
            status=deployment.status,
            success_count=deployment.success_count,
            failure_count=deployment.failure_count,
            initiated_by=deployment.initiated_by,
            recipient_emails=[recipient] if recipient else [],
        )

    await engine.dispose()
