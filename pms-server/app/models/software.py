import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class EndpointSoftware(Base):
    __tablename__ = "endpoint_software"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    endpoint_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    install_path: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(String(255))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    endpoint: Mapped["Endpoint"] = relationship(back_populates="software")

    __table_args__ = (
        UniqueConstraint("endpoint_id", "raw_name", name="uq_endpoint_software"),
        Index("idx_ep_sw_endpoint", "endpoint_id"),
    )
