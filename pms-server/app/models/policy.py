import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.database import Base


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # target_type: group | organization | endpoint
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    # patch_types: ["security", "critical", ...]
    patch_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=["security", "critical"])
    auto_install: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # install_window: {"days":["Mon","Tue"],"start":"02:00","end":"04:00","tz":"Asia/Seoul"}
    install_window: Mapped[dict | None] = mapped_column(JSONB)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    bandwidth_limit_kbps: Mapped[int | None] = mapped_column(Integer)
    pre_install_script: Mapped[str | None] = mapped_column(Text)
    post_install_script: Mapped[str | None] = mapped_column(Text)
    exception_patch_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    rollback_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    exceptions: Mapped[list["PolicyException"]] = relationship(back_populates="policy", cascade="all, delete-orphan")


class PolicyException(Base):
    __tablename__ = "policy_exceptions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False)
    endpoint_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False)
    patch_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("patches.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    policy: Mapped["Policy"] = relationship(back_populates="exceptions")
