from datetime import datetime
from pydantic import BaseModel


class PolicyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    organization_id: str | None = None
    priority: int = 100
    target_type: str          # group | organization | endpoint | all
    target_id: str
    patch_types: list[str] = ["security", "critical"]
    auto_install: bool = False
    install_window: dict | None = None
    max_concurrent: int = 10
    bandwidth_limit_kbps: int | None = None
    pre_install_script: str | None = None
    post_install_script: str | None = None
    exception_patch_ids: list[str] | None = None
    rollback_on_failure: bool = True


class PolicyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    priority: int | None = None
    patch_types: list[str] | None = None
    auto_install: bool | None = None
    install_window: dict | None = None
    max_concurrent: int | None = None
    bandwidth_limit_kbps: int | None = None
    rollback_on_failure: bool | None = None
    is_active: bool | None = None


class PolicyResponse(BaseModel):
    id: str
    name: str
    description: str | None
    organization_id: str | None
    priority: int
    target_type: str
    target_id: str
    patch_types: list[str]
    auto_install: bool
    install_window: dict | None
    max_concurrent: int
    bandwidth_limit_kbps: int | None
    rollback_on_failure: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PolicyExceptionRequest(BaseModel):
    endpoint_id: str
    patch_id: str | None = None
    reason: str | None = None
    expires_at: datetime | None = None


class DeploymentCreateRequest(BaseModel):
    patch_id: str
    policy_id: str | None = None
    target_type: str = "all"   # all | group | endpoint
    target_id: str | None = None
    scheduled_at: datetime | None = None


class DeploymentResultResponse(BaseModel):
    id: str
    endpoint_id: str
    status: str
    error_message: str | None
    exit_code: int | None
    download_started_at: datetime | None
    install_started_at: datetime | None
    completed_at: datetime | None
    rollback_snapshot_id: str | None
    model_config = {"from_attributes": True}


class DeploymentResponse(BaseModel):
    id: str
    patch_id: str
    policy_id: str | None
    initiated_by: str | None
    target_type: str
    target_id: str | None
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    status: str
    total_targets: int | None
    success_count: int
    failure_count: int
    created_at: datetime
    model_config = {"from_attributes": True}
