from datetime import datetime
from pydantic import BaseModel
from typing import Any


class AgentEnrollRequest(BaseModel):
    enrollment_token: str
    hostname: str
    fqdn: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    platform: str  # windows | linux
    os_name: str | None = None
    os_version: str | None = None
    os_build: str | None = None
    arch: str | None = None
    agent_version: str


class AgentEnrollResponse(BaseModel):
    agent_token: str
    endpoint_id: str
    server_time: datetime
    server_public_key: str | None = None  # 서명 검증용 공개키 (PEM)


class SystemMetrics(BaseModel):
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_free_gb: float | None = None


class HeartbeatRequest(BaseModel):
    agent_version: str
    timestamp: datetime
    system_metrics: SystemMetrics | None = None
    active_task_id: str | None = None
    pending_reboot: bool = False
    network_type: str | None = None


class HeartbeatResponse(BaseModel):
    server_time: datetime
    config_version: int
    has_pending_tasks: bool
    next_inventory_due: datetime | None = None


class TaskPayload(BaseModel):
    patch_id: str | None = None
    download_url: str | None = None
    file_hash_sha256: str | None = None
    file_signature: str | None = None        # RSA 서명 (base64)
    file_size_bytes: int | None = None
    delta_download_url: str | None = None    # 델타 패치 URL
    delta_hash_sha256: str | None = None     # 델타 파일 해시
    base_file_path: str | None = None        # 에이전트의 기존 파일 경로
    pre_install_script: str | None = None
    post_install_script: str | None = None
    requires_reboot: bool = False
    reboot_window: dict[str, str] | None = None
    bandwidth_limit_kbps: int | None = None
    rollback_snapshot_id: str | None = None


class AgentTask(BaseModel):
    task_id: str
    task_type: str  # patch_install | patch_rollback | inventory_now | config_update | agent_upgrade
    priority: int = 100
    created_at: datetime
    deadline: datetime | None = None
    payload: TaskPayload


class TaskStatusRequest(BaseModel):
    status: str  # pending | downloading | installing | success | failed | rolled_back | skipped
    progress: int | None = None
    error_message: str | None = None
    exit_code: int | None = None
    rollback_snapshot_id: str | None = None


class SoftwareItem(BaseModel):
    raw_name: str
    version: str
    install_path: str | None = None
    vendor: str | None = None


class InventoryRequest(BaseModel):
    collected_at: datetime
    software: list[SoftwareItem]
