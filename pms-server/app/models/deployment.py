import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey, Index, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    patch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("patches.id"), nullable=False)
    policy_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("policies.id"), nullable=True)
    initiated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False))  # user id, NULL = auto
    # target_type: group | endpoint | all
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # pending | in_progress | completed | failed | cancelled | rolled_back
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    total_targets: Mapped[int | None] = mapped_column(Integer)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    results: Mapped[list["DeploymentResult"]] = relationship(back_populates="deployment", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_deployments_status", "status"),
        Index("idx_deployments_patch", "patch_id"),
    )


class DeploymentResult(Base):
    __tablename__ = "deployment_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    deployment_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False)
    endpoint_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("endpoints.id"), nullable=False)
    # pending | downloading | installing | success | failed | rolled_back | skipped
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    download_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    install_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_snapshot_id: Mapped[str | None] = mapped_column(Text)

    deployment: Mapped["Deployment"] = relationship(back_populates="results")

    __table_args__ = (
        Index("idx_dr_deployment", "deployment_id"),
        Index("idx_dr_endpoint", "endpoint_id"),
        Index("idx_dr_status", "status"),
    )
