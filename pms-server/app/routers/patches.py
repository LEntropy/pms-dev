import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError, ConflictError
from app.models.patch import SoftwareVendor, SoftwareProduct, Patch
from app.models.user import User
from app.schemas.patch import (
    VendorResponse, VendorCreateRequest,
    ProductResponse, ProductCreateRequest,
    PatchResponse, PatchCreateRequest, PatchListResponse,
)
from app.services.file_distribution import upload_patch, delete_patch_file

router = APIRouter(prefix="/patches", tags=["patches"])


# ── Vendors ──────────────────────────────────────────────────────────────────

@router.get("/vendors", response_model=list[VendorResponse])
async def list_vendors(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(select(SoftwareVendor).order_by(SoftwareVendor.name))
    return [VendorResponse.model_validate(v) for v in result.scalars()]


@router.post("/vendors", response_model=VendorResponse, status_code=201)
async def create_vendor(
    body: VendorCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    existing = await db.execute(select(SoftwareVendor).where(SoftwareVendor.slug == body.slug))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Vendor slug '{body.slug}' already exists")
    vendor = SoftwareVendor(id=str(uuid.uuid4()), name=body.name, slug=body.slug)
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return VendorResponse.model_validate(vendor)


# ── Products ─────────────────────────────────────────────────────────────────

@router.get("/products", response_model=list[ProductResponse])
async def list_products(
    vendor_id: str | None = None,
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(SoftwareProduct)
    if vendor_id:
        q = q.where(SoftwareProduct.vendor_id == vendor_id)
    if platform:
        q = q.where(SoftwareProduct.platform.in_([platform, "both"]))
    result = await db.execute(q.order_by(SoftwareProduct.name))
    return [ProductResponse.model_validate(p) for p in result.scalars()]


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    body: ProductCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    product = SoftwareProduct(
        id=str(uuid.uuid4()),
        vendor_id=body.vendor_id,
        name=body.name,
        slug=body.slug,
        platform=body.platform,
        detection_rule=body.detection_rule,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return ProductResponse.model_validate(product)


# ── Patches ──────────────────────────────────────────────────────────────────

@router.get("", response_model=PatchListResponse)
async def list_patches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    product_id: str | None = None,
    patch_type: str | None = None,
    severity: str | None = None,
    cve: str | None = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Patch).where(Patch.is_active == is_active)
    if product_id:
        q = q.where(Patch.product_id == product_id)
    if patch_type:
        q = q.where(Patch.patch_type == patch_type)
    if severity:
        q = q.where(Patch.severity == severity)
    if cve:
        q = q.where(Patch.cve_ids.contains([cve]))

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(Patch.release_date.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = [PatchResponse.model_validate(p) for p in result.scalars()]

    return PatchListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{patch_id}", response_model=PatchResponse)
async def get_patch(
    patch_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Patch).where(Patch.id == patch_id))
    patch = result.scalar_one_or_none()
    if not patch:
        raise NotFoundError("Patch not found")
    return PatchResponse.model_validate(patch)


@router.post("", response_model=PatchResponse, status_code=201)
async def create_patch_with_file(
    file: UploadFile = File(...),
    product_id: str = Form(...),
    version: str = Form(...),
    title: str = Form(...),
    patch_type: str = Form(...),
    release_date: str = Form(...),
    previous_version: str | None = Form(None),
    severity: str | None = Form(None),
    description: str | None = Form(None),
    cve_ids: str | None = Form(None),   # comma-separated: "CVE-2024-1234,CVE-2024-5678"
    kb_article: str | None = Form(None),
    requires_reboot: bool = Form(False),
    rollback_supported: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin", "operator")),
):
    from datetime import date as date_type
    file_data = await file.read()
    object_name = f"{product_id}/{version}/{file.filename}"
    obj_name, sha256, size = await upload_patch(file_data, object_name)

    parsed_cve = [c.strip() for c in cve_ids.split(",")] if cve_ids else None
    parsed_date = date_type.fromisoformat(release_date)

    patch = Patch(
        id=str(uuid.uuid4()),
        product_id=product_id,
        version=version,
        previous_version=previous_version,
        patch_type=patch_type,
        severity=severity,
        title=title,
        description=description,
        cve_ids=parsed_cve,
        kb_article=kb_article,
        release_date=parsed_date,
        file_path=obj_name,
        file_size_bytes=size,
        file_hash_sha256=sha256,
        requires_reboot=requires_reboot,
        rollback_supported=rollback_supported,
        created_at=datetime.now(timezone.utc),
    )
    db.add(patch)
    await db.commit()
    await db.refresh(patch)

    # 자사 SW 자동 배포 트리거
    await _trigger_auto_deployments(db, patch)

    return PatchResponse.model_validate(patch)


async def _trigger_auto_deployments(db: AsyncSession, patch: Patch) -> None:
    """WatchedProduct 설정에 맞는 새 패치가 업로드되면 배포를 자동 생성한다."""
    from app.models.catalog import WatchedProduct
    from app.models.deployment import Deployment
    from app.tasks.deployment_tasks import schedule_deployment
    from datetime import datetime, timezone

    result = await db.execute(
        select(WatchedProduct).where(
            WatchedProduct.product_id == patch.product_id,
            WatchedProduct.is_active == True,
        )
    )
    watchers = result.scalars().all()

    for watcher in watchers:
        if patch.patch_type not in watcher.patch_types:
            continue

        deployment = Deployment(
            id=str(uuid.uuid4()),
            patch_id=patch.id,
            policy_id=watcher.policy_id,
            initiated_by=watcher.created_by,
            target_type=watcher.target_type,
            target_id=watcher.target_id,
            status="pending",
            success_count=0,
            failure_count=0,
            created_at=datetime.now(timezone.utc),
        )
        db.add(deployment)
        await db.commit()
        await db.refresh(deployment)

        schedule_deployment.delay(deployment.id)


@router.delete("/{patch_id}", status_code=204)
async def retire_patch(
    patch_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(Patch).where(Patch.id == patch_id))
    patch = result.scalar_one_or_none()
    if not patch:
        raise NotFoundError("Patch not found")
    patch.is_active = False
    db.add(patch)
    await db.commit()


@router.get("/{patch_id}/affected-endpoints")
async def affected_endpoints(
    patch_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """이 패치가 필요한 엔드포인트 목록 (인벤토리 기반 버전 비교)."""
    from app.services.compliance import get_affected_endpoints
    return await get_affected_endpoints(db, patch_id)
