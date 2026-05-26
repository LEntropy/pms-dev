import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from app.database import Base


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    fqdn: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv4/IPv6
    mac_address: Mapped[str | None] = mapped_column(String(17))
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # windows | linux
    os_name: Mapped[str | None] = mapped_column(String(128))
    os_version: Mapped[str | None] = mapped_column(String(64))
    os_build: Mapped[str | None] = mapped_column(String(64))
    arch: Mapped[str | None] = mapped_column(String(16))
    agent_version: Mapped[str | None] = mapped_column(String(32))
    agent_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True
    )
    group_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("endpoint_groups.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active | inactive | quarantined | decommissioned
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    organization: Mapped["Organization"] = relationship(back_populates="endpoints")
    group: Mapped["EndpointGroup | None"] = relationship(back_populates="endpoints")
    group_memberships: Mapped[list["EndpointGroupMember"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
    software: Mapped[list["EndpointSoftware"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_endpoints_org", "organization_id"),
        Index("idx_endpoints_status", "status"),
        Index("idx_endpoints_last_seen", "last_seen_at"),
    )


class EndpointGroup(Base):
    __tablename__ = "endpoint_groups"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True
    )
    membership_rule: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    organization: Mapped["Organization"] = relationship(back_populates="groups")
    endpoints: Mapped[list["Endpoint"]] = relationship(back_populates="group")
    members: Mapped[list["EndpointGroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class EndpointGroupMember(Base):
    __tablename__ = "endpoint_group_members"

    endpoint_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("endpoint_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    endpoint: Mapped["Endpoint"] = relationship(back_populates="group_memberships")
    group: Mapped["EndpointGroup"] = relationship(back_populates="members")
