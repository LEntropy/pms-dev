"""
정책 엔진 — 엔드포인트에 적용할 유효 정책을 결정하고
설치 윈도우(시간대/요일)를 검증합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import Endpoint, EndpointGroup, EndpointGroupMember
from app.models.policy import Policy, PolicyException
from app.models.patch import Patch

logger = logging.getLogger(__name__)


# ── 정책 우선순위 해석 ────────────────────────────────────────────────────────

async def resolve_policy(db: AsyncSession, endpoint: Endpoint, patch: Patch) -> Policy | None:
    """
    엔드포인트 + 패치 조합에 대해 적용할 정책을 반환합니다.
    우선순위 낮은 숫자(priority 값) = 더 높은 우선순위.
    """
    # 엔드포인트가 속한 그룹 ID 목록 수집
    group_ids = await _get_endpoint_group_ids(db, endpoint)

    # 활성 정책을 우선순위 순으로 조회
    result = await db.execute(
        select(Policy)
        .where(Policy.is_active == True)
        .order_by(Policy.priority.asc())
    )
    policies = result.scalars().all()

    for policy in policies:
        # 타겟 매칭 확인
        if not _matches_target(policy, endpoint, group_ids):
            continue

        # 패치 유형 포함 여부 확인
        if patch.patch_type not in policy.patch_types:
            continue

        # 예외 패치 확인
        if policy.exception_patch_ids and patch.id in policy.exception_patch_ids:
            continue

        # 엔드포인트별 예외 확인
        if await _has_endpoint_exception(db, policy.id, endpoint.id, patch.id):
            continue

        return policy

    return None


def _matches_target(policy: Policy, endpoint: Endpoint, group_ids: set[str]) -> bool:
    if policy.target_type == "all":
        return True
    if policy.target_type == "endpoint":
        return policy.target_id == endpoint.id
    if policy.target_type == "organization":
        return policy.target_id == endpoint.organization_id
    if policy.target_type == "group":
        return policy.target_id in group_ids
    return False


async def _get_endpoint_group_ids(db: AsyncSession, endpoint: Endpoint) -> set[str]:
    """엔드포인트가 속한 그룹 ID 전체 (명시적 + 기본 그룹)."""
    group_ids: set[str] = set()
    if endpoint.group_id:
        group_ids.add(endpoint.group_id)

    result = await db.execute(
        select(EndpointGroupMember.group_id)
        .where(EndpointGroupMember.endpoint_id == endpoint.id)
    )
    for row in result:
        group_ids.add(row[0])

    return group_ids


async def _has_endpoint_exception(
    db: AsyncSession, policy_id: str, endpoint_id: str, patch_id: str
) -> bool:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PolicyException).where(
            PolicyException.policy_id == policy_id,
            PolicyException.endpoint_id == endpoint_id,
            (PolicyException.patch_id == patch_id) | (PolicyException.patch_id == None),
            (PolicyException.expires_at == None) | (PolicyException.expires_at > now),
        )
    )
    return result.scalar_one_or_none() is not None


# ── 설치 윈도우 검증 ──────────────────────────────────────────────────────────

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def is_within_install_window(policy: Policy) -> bool:
    """
    policy.install_window 형식:
    {
      "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
      "start": "02:00",
      "end":   "04:00",
      "tz":    "Asia/Seoul"
    }
    install_window가 없으면 항상 True (제한 없음).
    """
    window = policy.install_window
    if not window:
        return True

    tz_name = window.get("tz", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    current_day = DAY_NAMES[now.weekday()]
    allowed_days = window.get("days", DAY_NAMES)

    if current_day not in allowed_days:
        return False

    start_h, start_m = map(int, window["start"].split(":"))
    end_h, end_m = map(int, window["end"].split(":"))
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes < end_minutes
    # 자정을 넘는 윈도우 (예: 22:00 ~ 02:00)
    return current_minutes >= start_minutes or current_minutes < end_minutes


# ── 배포 대상 엔드포인트 확장 ─────────────────────────────────────────────────

async def expand_targets(
    db: AsyncSession, target_type: str, target_id: str | None
) -> list[str]:
    """
    배포 대상을 개별 endpoint_id 목록으로 확장합니다.
    target_type: "all" | "group" | "endpoint"
    """
    if target_type == "endpoint" and target_id:
        return [target_id]

    if target_type == "all":
        result = await db.execute(
            select(Endpoint.id).where(Endpoint.status == "active")
        )
        return [row[0] for row in result]

    if target_type == "group" and target_id:
        # 명시적 그룹 멤버
        explicit = await db.execute(
            select(EndpointGroupMember.endpoint_id)
            .where(EndpointGroupMember.group_id == target_id)
        )
        ids = {row[0] for row in explicit}

        # 기본 그룹(group_id 컬럼)으로 속한 엔드포인트
        default_group = await db.execute(
            select(Endpoint.id).where(
                Endpoint.group_id == target_id,
                Endpoint.status == "active",
            )
        )
        for row in default_group:
            ids.add(row[0])

        return list(ids)

    return []


# ── 정책 시뮬레이션 ───────────────────────────────────────────────────────────

async def simulate_policy(
    db: AsyncSession, policy: Policy, patch: Patch
) -> dict:
    """
    정책 적용 시 영향을 받는 엔드포인트를 dry-run으로 반환합니다.
    실제 배포는 하지 않습니다.
    """
    endpoint_ids = await expand_targets(db, policy.target_type, policy.target_id)

    affected = []
    skipped_exception = []

    for ep_id in endpoint_ids:
        ep_result = await db.execute(select(Endpoint).where(Endpoint.id == ep_id))
        ep = ep_result.scalar_one_or_none()
        if not ep:
            continue

        if await _has_endpoint_exception(db, policy.id, ep_id, patch.id):
            skipped_exception.append(ep_id)
        else:
            affected.append(ep_id)

    return {
        "policy_id": policy.id,
        "patch_id": patch.id,
        "total_targets": len(endpoint_ids),
        "affected": len(affected),
        "skipped_by_exception": len(skipped_exception),
        "within_install_window": is_within_install_window(policy),
        "affected_endpoint_ids": affected,
    }
