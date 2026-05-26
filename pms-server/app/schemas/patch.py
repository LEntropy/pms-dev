from datetime import datetime, date
from pydantic import BaseModel


class VendorResponse(BaseModel):
    id: str
    name: str
    slug: str
    model_config = {"from_attributes": True}


class VendorCreateRequest(BaseModel):
    name: str
    slug: str


class ProductResponse(BaseModel):
    id: str
    vendor_id: str
    name: str
    slug: str
    platform: str
    detection_rule: dict
    model_config = {"from_attributes": True}


class ProductCreateRequest(BaseModel):
    vendor_id: str
    name: str
    slug: str
    platform: str
    detection_rule: dict = {}


class PatchResponse(BaseModel):
    id: str
    product_id: str
    version: str
    previous_version: str | None
    patch_type: str
    severity: str | None
    title: str
    description: str | None
    cve_ids: list[str] | None
    kb_article: str | None
    release_date: date
    file_path: str
    file_size_bytes: int | None
    file_hash_sha256: str
    is_active: bool
    requires_reboot: bool
    rollback_supported: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class PatchCreateRequest(BaseModel):
    product_id: str
    version: str
    previous_version: str | None = None
    patch_type: str
    severity: str | None = None
    title: str
    description: str | None = None
    cve_ids: list[str] | None = None
    kb_article: str | None = None
    release_date: date
    requires_reboot: bool = False
    rollback_supported: bool = True


class PatchListResponse(BaseModel):
    items: list[PatchResponse]
    total: int
    page: int
    page_size: int


class ComplianceItem(BaseModel):
    patch_id: str
    patch_title: str
    patch_version: str
    installed_version: str | None
    severity: str | None
    patch_type: str
    status: str  # missing | compliant | newer


class EndpointComplianceResponse(BaseModel):
    endpoint_id: str
    total_patches: int
    missing: int
    compliant: int
    compliance_pct: float
    items: list[ComplianceItem]
