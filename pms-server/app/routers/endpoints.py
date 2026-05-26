from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.redis import get_redis, endpoint_online_key
from app.core.exceptions import NotFoundError
from app.models.endpoint import Endpoint
from app.models.user import User
from app.schemas.endpoint import EndpointResponse, EndpointListResponse, EndpointUpdateRequest

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


async def _enrich_with_online_status(endpoints: list[Endpoint], redis) -> list[EndpointResponse]:
    results = []
    for ep in endpoints:
        is_online = bool(await redis.exists(endpoint_online_key(ep.id)))
        resp = EndpointResponse.model_validate(ep)
        resp.is_online = is_online
        results.append(resp)
    return results


@router.get("", response_model=EndpointListResponse)
async def list_endpoints(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = None,
    platform: str | None = None,
    organization_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Endpoint)
    if status:
        query = query.where(Endpoint.status == status)
    if platform:
        query = query.where(Endpoint.platform == platform)
    if organization_id:
        query = query.where(Endpoint.organization_id == organization_id)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.offset((page - 1) * page_size).limit(page_size).order_by(Endpoint.enrolled_at.desc())
    result = await db.execute(query)
    endpoints = result.scalars().all()

    redis = await get_redis()
    items = await _enrich_with_online_status(list(endpoints), redis)

    return EndpointListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{endpoint_id}", response_model=EndpointResponse)
async def get_endpoint(
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise NotFoundError("Endpoint not found")

    redis = await get_redis()
    is_online = bool(await redis.exists(endpoint_online_key(endpoint.id)))
    resp = EndpointResponse.model_validate(endpoint)
    resp.is_online = is_online
    return resp


@router.patch("/{endpoint_id}", response_model=EndpointResponse)
async def update_endpoint(
    endpoint_id: str,
    body: EndpointUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin", "operator")),
):
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise NotFoundError("Endpoint not found")

    if body.group_id is not None:
        endpoint.group_id = body.group_id
    if body.organization_id is not None:
        endpoint.organization_id = body.organization_id
    if body.metadata is not None:
        endpoint.metadata_ = body.metadata

    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)

    redis = await get_redis()
    is_online = bool(await redis.exists(endpoint_online_key(endpoint.id)))
    resp = EndpointResponse.model_validate(endpoint)
    resp.is_online = is_online
    return resp


@router.post("/{endpoint_id}/quarantine")
async def quarantine_endpoint(
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise NotFoundError("Endpoint not found")

    endpoint.status = "quarantined"
    db.add(endpoint)
    await db.commit()
    return {"id": endpoint_id, "status": "quarantined"}


@router.delete("/{endpoint_id}")
async def decommission_endpoint(
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise NotFoundError("Endpoint not found")

    endpoint.status = "decommissioned"
    db.add(endpoint)
    await db.commit()
    return {"id": endpoint_id, "status": "decommissioned"}


@router.get("/stats/summary")
async def endpoint_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Endpoint.status, func.count().label("count"))
        .group_by(Endpoint.status)
    )
    status_counts = {row.status: row.count for row in result}

    platform_result = await db.execute(
        select(Endpoint.platform, func.count().label("count"))
        .where(Endpoint.status != "decommissioned")
        .group_by(Endpoint.platform)
    )
    platform_counts = {row.platform: row.count for row in platform_result}

    return {
        "by_status": status_counts,
        "by_platform": platform_counts,
        "total": sum(status_counts.values()),
    }


@router.get("/{endpoint_id}/software")
async def get_endpoint_software(
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.software import EndpointSoftware
    result = await db.execute(
        select(Endpoint).where(Endpoint.id == endpoint_id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Endpoint not found")

    sw_result = await db.execute(
        select(EndpointSoftware)
        .where(EndpointSoftware.endpoint_id == endpoint_id)
        .order_by(EndpointSoftware.raw_name)
    )
    items = sw_result.scalars().all()
    return {
        "endpoint_id": endpoint_id,
        "total": len(items),
        "software": [
            {
                "raw_name": s.raw_name,
                "version": s.version,
                "vendor": s.vendor,
                "install_path": s.install_path,
                "detected_at": s.detected_at.isoformat(),
            }
            for s in items
        ],
    }


@router.get("/{endpoint_id}/compliance")
async def get_endpoint_compliance(
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.compliance import get_endpoint_compliance as calc
    result = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    if not result.scalar_one_or_none():
        raise NotFoundError("Endpoint not found")
    return await calc(db, endpoint_id)


@router.get("/compliance/summary")
async def compliance_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.compliance import get_org_compliance_summary
    return await get_org_compliance_summary(db)
