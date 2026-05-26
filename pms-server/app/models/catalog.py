"""자사 SW 자동 배포 감시 목록."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.database import Base


class WatchedProduct(Base):
    """
    특정 SoftwareProduct에 새 패치가 업로드되면 자동으로 배포를 트리거한다.
    """
    __tablename__ = "watched_products"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("software_products.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    target_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    policy_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("policies.id"))
    patch_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=["security", "critical"])
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
