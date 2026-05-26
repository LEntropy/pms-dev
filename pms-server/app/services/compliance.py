"""
컴플라이언스 엔진 — 에이전트 인벤토리와 패치 카탈로그를 비교해
각 엔드포인트의 누락 패치를 계산합니다.

버전 비교 전략:
  1. packaging.version (PEP 440 / SemVer) 우선 시도
  2. 실패 시 tuple 기반 숫자 비교 (1.2.3 → (1,2,3))
  3. 최후 수단 문자열 비교
"""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patch import Patch, SoftwareProduct
from app.models.software import EndpointSoftware
from app.models.endpoint import Endpoint
from app.schemas.patch import ComplianceItem, EndpointComplianceResponse

logger = logging.getLogger(__name__)


# ── Version comparison ────────────────────────────────────────────────────────

def _version_tuple(v: str) -> tuple:
    """'1.2.3.4' → (1, 2, 3, 4)  —  non-numeric parts treated as 0."""
    parts = []
    for segment in v.replace("-", ".").split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def compare_versions(installed: str | None, required: str | None) -> int:
    """
    Returns:
      -1  installed < required  (패치 필요)
       0  installed == required (최신)
       1  installed > required  (더 새 버전 설치됨)
    """
    if not installed:
        return -1
    if not required:
        return 0

    try:
        from packaging.version import Version
        iv, rv = Version(installed), Version(required)
        if iv < rv:
            return -1
        if iv > rv:
            return 1
        return 0
    except Exception:
        it, rt = _version_tuple(installed), _version_tuple(required)
        if it < rt:
            return -1
        if it > rt:
            return 1
        return 0


# ── Per-endpoint compliance ───────────────────────────────────────────────────

async def get_endpoint_compliance(
    db: AsyncSession, endpoint_id: str
) -> EndpointComplianceResponse:
    """
    단일 엔드포인트에 대한 컴플라이언스 계산.
    installed software × active patches → missing / compliant / newer
    """
    # 설치된 소프트웨어 (raw_name → version)
    sw_result = await db.execute(
        select(EndpointSoftware).where(EndpointSoftware.endpoint_id == endpoint_id)
    )
    installed: dict[str, str] = {
        row.raw_name.lower(): row.version for row in sw_result.scalars()
    }

    # 활성 패치 + 제품명 조인
    patch_result = await db.execute(
        select(Patch, SoftwareProduct)
        .join(SoftwareProduct, Patch.product_id == SoftwareProduct.id)
        .where(Patch.is_active == True)
    )

    items: list[ComplianceItem] = []
    for patch, product in patch_result:
        # product.name 또는 slug로 인벤토리와 매칭 (대소문자 무시)
        inst_version = (
            installed.get(product.name.lower())
            or installed.get(product.slug.lower())
        )

        if inst_version is None:
            status = "missing"
        else:
            cmp = compare_versions(inst_version, patch.version)
            if cmp < 0:
                status = "missing"
            elif cmp == 0:
                status = "compliant"
            else:
                status = "newer"

        items.append(ComplianceItem(
            patch_id=patch.id,
            patch_title=patch.title,
            patch_version=patch.version,
            installed_version=inst_version,
            severity=patch.severity,
            patch_type=patch.patch_type,
            status=status,
        ))

    total = len(items)
    compliant_count = sum(1 for i in items if i.status in ("compliant", "newer"))
    missing_count = sum(1 for i in items if i.status == "missing")
    pct = (compliant_count / total * 100) if total else 100.0

    return EndpointComplianceResponse(
        endpoint_id=endpoint_id,
        total_patches=total,
        missing=missing_count,
        compliant=compliant_count,
        compliance_pct=round(pct, 1),
        items=items,
    )


async def get_affected_endpoints(db: AsyncSession, patch_id: str) -> dict:
    """특정 패치가 필요한 (missing) 엔드포인트 목록."""
    patch_result = await db.execute(
        select(Patch, SoftwareProduct)
        .join(SoftwareProduct, Patch.product_id == SoftwareProduct.id)
        .where(Patch.id == patch_id, Patch.is_active == True)
    )
    row = patch_result.first()
    if not row:
        return {"patch_id": patch_id, "affected": []}

    patch, product = row

    # 설치된 버전이 패치 버전보다 낮은 엔드포인트 찾기
    sw_result = await db.execute(
        select(EndpointSoftware)
        .where(
            EndpointSoftware.raw_name.ilike(f"%{product.name}%")
        )
    )

    affected_ids = []
    for sw in sw_result.scalars():
        if compare_versions(sw.version, patch.version) < 0:
            affected_ids.append({"endpoint_id": sw.endpoint_id, "installed_version": sw.version})

    return {
        "patch_id": patch_id,
        "patch_version": patch.version,
        "product_name": product.name,
        "affected_count": len(affected_ids),
        "affected": affected_ids,
    }


async def get_org_compliance_summary(db: AsyncSession) -> dict:
    """전체 조직의 컴플라이언스 요약 (대시보드 차트용)."""
    ep_result = await db.execute(
        select(Endpoint.id).where(Endpoint.status == "active")
    )
    endpoint_ids = [row[0] for row in ep_result]

    if not endpoint_ids:
        return {"total_endpoints": 0, "avg_compliance_pct": 100.0, "endpoints": []}

    summaries = []
    for ep_id in endpoint_ids[:100]:  # 대규모일 경우 배치 처리 필요
        try:
            result = await get_endpoint_compliance(db, ep_id)
            summaries.append({
                "endpoint_id": ep_id,
                "compliance_pct": result.compliance_pct,
                "missing": result.missing,
            })
        except Exception as exc:
            logger.warning("Compliance calc failed for %s: %s", ep_id, exc)

    avg_pct = (
        sum(s["compliance_pct"] for s in summaries) / len(summaries)
        if summaries else 100.0
    )

    return {
        "total_endpoints": len(endpoint_ids),
        "avg_compliance_pct": round(avg_pct, 1),
        "endpoints": summaries,
    }
