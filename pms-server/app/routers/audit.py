from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.deps import require_role
from app.models.audit import AuditLog
from app.models.user import User
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: int
    actor_type: str
    actor_id: str | None
    action: str
    resource: str | None
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    occurred_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    actor_id: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    q = select(AuditLog).order_by(AuditLog.occurred_at.desc())
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if resource:
        q = q.where(AuditLog.resource == resource)
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    return [AuditLogResponse.model_validate(row) for row in result.scalars()]
