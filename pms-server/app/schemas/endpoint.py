from datetime import datetime
from pydantic import BaseModel
from typing import Any


class EndpointResponse(BaseModel):
    id: str
    hostname: str
    fqdn: str | None
    ip_address: str | None
    platform: str
    os_name: str | None
    os_version: str | None
    agent_version: str | None
    organization_id: str | None
    group_id: str | None
    status: str
    last_seen_at: datetime | None
    enrolled_at: datetime
    is_online: bool = False

    model_config = {"from_attributes": True}


class EndpointListResponse(BaseModel):
    items: list[EndpointResponse]
    total: int
    page: int
    page_size: int


class EndpointUpdateRequest(BaseModel):
    group_id: str | None = None
    organization_id: str | None = None
    metadata: dict[str, Any] | None = None


class EnrollmentTokenRequest(BaseModel):
    label: str | None = None
    organization_id: str | None = None
    expires_hours: int = 24


class EnrollmentTokenResponse(BaseModel):
    token: str
    expires_at: datetime
