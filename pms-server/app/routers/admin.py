"""
시스템 관리 API.
- LDAP/AD 수동 동기화
- PDF 리포트 즉시 생성 + 목록 조회
- OpenVAS 스캔 트리거
- 자사 SW 자동 배포(WatchedProduct) CRUD
- 에이전트 바이너리 서명 공개키 조회
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.deps import require_role
from app.models.user import User
from app.models.catalog import WatchedProduct

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── LDAP ─────────────────────────────────────────────────────────────────────

@router.post("/ldap/sync")
async def trigger_ldap_sync(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin")),
):
    """LDAP/AD 즉시 동기화 (Celery 태스크로 위임)."""
    from app.tasks.sync_tasks import ldap_sync
    task = ldap_sync.delay()
    return {"task_id": task.id, "status": "queued"}


@router.get("/ldap/status")
async def ldap_status(_: User = Depends(require_role("superadmin", "admin"))):
    """LDAP 연결 상태 확인."""
    from app.config import settings

    if not settings.ldap_url:
        return {"configured": False}

    from app.services.ldap_sync import _get_ldap_conn
    conn = _get_ldap_conn()
    return {"configured": True, "connected": conn is not None}


# ─── 리포트 ────────────────────────────────────────────────────────────────────

@router.post("/reports/compliance")
async def generate_compliance_report_now(
    _: User = Depends(require_role("superadmin", "admin")),
):
    """컴플라이언스 PDF 리포트 즉시 생성 (비동기)."""
    from app.tasks.report_tasks import generate_report_on_demand
    task = generate_report_on_demand.delay("compliance")
    return {"task_id": task.id, "status": "generating"}


@router.get("/reports")
async def list_reports(_: User = Depends(require_role("superadmin", "admin"))):
    """MinIO에 저장된 리포트 목록 반환."""
    from app.services.file_distribution import _get_minio_client
    from app.config import settings

    client = _get_minio_client()
    objects = list(client.list_objects(settings.minio_bucket_patches, prefix="reports/"))
    return {
        "reports": [
            {
                "name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            }
            for obj in objects
        ]
    }


@router.get("/reports/{report_name:path}/download-url")
async def get_report_download_url(
    report_name: str,
    _: User = Depends(require_role("superadmin", "admin")),
):
    """리포트 파일 서명된 다운로드 URL 반환."""
    from app.services.file_distribution import _get_minio_client
    from app.config import settings
    from datetime import timedelta

    client = _get_minio_client()
    url = client.presigned_get_object(
        settings.minio_bucket_patches,
        report_name,
        expires=timedelta(seconds=settings.minio_presigned_url_expire_seconds),
    )
    return {"download_url": url}


# ─── OpenVAS ───────────────────────────────────────────────────────────────────

@router.post("/openvas/scan")
async def trigger_openvas_scan(
    _: User = Depends(require_role("superadmin", "admin")),
):
    """OpenVAS 취약점 스캔 즉시 트리거."""
    from app.tasks.sync_tasks import openvas_scan
    task = openvas_scan.delay()
    return {"task_id": task.id, "status": "queued"}


# ─── 자사 SW 자동 배포 (WatchedProduct) ─────────────────────────────────────────

class WatchedProductCreate(BaseModel):
    product_id: str
    target_type: str = "all"
    target_id: str | None = None
    policy_id: str | None = None
    patch_types: list[str] = ["security", "critical"]


class WatchedProductResponse(BaseModel):
    id: str
    product_id: str
    target_type: str
    target_id: str | None
    policy_id: str | None
    patch_types: list[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/watched-products", response_model=list[WatchedProductResponse])
async def list_watched_products(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(WatchedProduct).where(WatchedProduct.is_active == True))
    return [WatchedProductResponse.model_validate(w) for w in result.scalars()]


@router.post("/watched-products", response_model=WatchedProductResponse, status_code=201)
async def create_watched_product(
    body: WatchedProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("superadmin", "admin")),
):
    wp = WatchedProduct(
        id=str(uuid.uuid4()),
        product_id=body.product_id,
        target_type=body.target_type,
        target_id=body.target_id,
        policy_id=body.policy_id,
        patch_types=body.patch_types,
        is_active=True,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(wp)
    await db.commit()
    await db.refresh(wp)
    return WatchedProductResponse.model_validate(wp)


@router.delete("/watched-products/{wp_id}")
async def delete_watched_product(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    result = await db.execute(select(WatchedProduct).where(WatchedProduct.id == wp_id))
    wp = result.scalar_one_or_none()
    if wp:
        wp.is_active = False
        db.add(wp)
        await db.commit()
    return {"id": wp_id, "status": "deactivated"}


# ─── 에이전트 서명 공개키 ──────────────────────────────────────────────────────

@router.get("/signing/public-key")
async def get_signing_public_key(
    _: User = Depends(require_role("superadmin", "admin")),
):
    """에이전트 배포용 서명 검증 공개키 반환."""
    from app.config import settings
    from app.core.signing import get_public_key_pem
    import os

    if not os.path.exists(settings.jwt_public_key_path):
        return {"public_key": None, "message": "Public key not found"}
    pem = get_public_key_pem(settings.jwt_public_key_path)
    return {"public_key": pem}


# ─── 델타 패치 생성 ────────────────────────────────────────────────────────────

class DeltaPatchRequest(BaseModel):
    patch_id: str
    base_patch_id: str  # 이전 버전 패치 ID


@router.post("/delta-patches")
async def create_delta_patch(
    body: DeltaPatchRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("superadmin", "admin")),
):
    """두 패치 파일 간 델타를 생성하고 MinIO에 업로드한다."""
    from app.models.patch import Patch
    from app.services.file_distribution import _get_minio_client
    from app.services.delta_patch import upload_delta_for_patch
    from app.config import settings
    import tempfile

    result = await db.execute(select(Patch).where(Patch.id == body.patch_id))
    new_patch = result.scalar_one_or_none()
    result2 = await db.execute(select(Patch).where(Patch.id == body.base_patch_id))
    base_patch = result2.scalar_one_or_none()

    if not new_patch or not base_patch:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Patch not found")

    minio = _get_minio_client()

    # 두 패치 파일을 임시 디렉토리에 다운로드
    with tempfile.TemporaryDirectory() as tmpdir:
        base_file = f"{tmpdir}/base"
        new_file = f"{tmpdir}/new"
        minio.fget_object(settings.minio_bucket_patches, base_patch.file_path, base_file)
        minio.fget_object(settings.minio_bucket_patches, new_patch.file_path, new_file)

        delta_info = await upload_delta_for_patch(body.patch_id, base_file, new_file)

    # patches 레코드 갱신
    new_patch.delta_patch_path = delta_info["delta_object"]
    new_patch.delta_hash_sha256 = delta_info["delta_hash"]
    db.add(new_patch)
    await db.commit()

    return {
        "patch_id": body.patch_id,
        "delta_object": delta_info["delta_object"],
        "delta_hash": delta_info["delta_hash"],
        "reduction_pct": delta_info["reduction_pct"],
    }
