import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError
from app.models.policy import Policy, PolicyException
from app.models.patch import Patch
from app.models.user import User
from app.schemas.policy import (
    PolicyCreateRequest, PolicyUpdateRequest, PolicyResponse,
    PolicyExceptionRequest,
)
from app.services.policy_engine import simulate_policy

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=list[PolicyResponse])
async def list_policies(
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Policy).where(Policy.is_active == is_active).order_by(Policy.priority)
    )
    return [PolicyResponse.model_validate(p) for p in result.scalars()]


@router.post("", response_model=PolicyResponse, status_code=201)
async def create_policy(
    body: PolicyCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    now = datetime.now(timezone.utc)
    policy = Policy(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        **body.model_dump(),
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return PolicyResponse.model_validate(policy)


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise NotFoundError("Policy not found")
    return PolicyResponse.model_validate(policy)


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    body: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise NotFoundError("Policy not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(policy, field, value)
    policy.updated_at = datetime.now(timezone.utc)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return PolicyResponse.model_validate(policy)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise NotFoundError("Policy not found")
    policy.is_active = False
    policy.updated_at = datetime.now(timezone.utc)
    db.add(policy)
    await db.commit()


@router.post("/{policy_id}/exceptions", status_code=201)
async def add_exception(
    policy_id: str,
    body: PolicyExceptionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin", "operator")),
):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    if not result.scalar_one_or_none():
        raise NotFoundError("Policy not found")

    exc = PolicyException(
        id=str(uuid.uuid4()),
        policy_id=policy_id,
        endpoint_id=body.endpoint_id,
        patch_id=body.patch_id,
        reason=body.reason,
        expires_at=body.expires_at,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(exc)
    await db.commit()
    return {"id": exc.id, "policy_id": policy_id}


@router.delete("/{policy_id}/exceptions/{exception_id}", status_code=204)
async def remove_exception(
    policy_id: str,
    exception_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(
        select(PolicyException).where(
            PolicyException.id == exception_id,
            PolicyException.policy_id == policy_id,
        )
    )
    exc = result.scalar_one_or_none()
    if not exc:
        raise NotFoundError("Exception not found")
    await db.delete(exc)
    await db.commit()


@router.post("/{policy_id}/simulate")
async def simulate(
    policy_id: str,
    patch_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """정책 적용 시 영향받는 엔드포인트를 dry-run으로 반환합니다."""
    pol_res = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = pol_res.scalar_one_or_none()
    if not policy:
        raise NotFoundError("Policy not found")

    pat_res = await db.execute(select(Patch).where(Patch.id == patch_id))
    patch = pat_res.scalar_one_or_none()
    if not patch:
        raise NotFoundError("Patch not found")

    return await simulate_policy(db, policy, patch)
