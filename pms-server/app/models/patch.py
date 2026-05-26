import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, Boolean, BigInteger, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.database import Base


class SoftwareVendor(Base):
    __tablename__ = "software_vendors"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    products: Mapped[list["SoftwareProduct"]] = relationship(back_populates="vendor")


class SoftwareProduct(Base):
    __tablename__ = "software_products"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("software_vendors.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # windows | linux | both
    # JSON rule describing how agent detects installed version
    # e.g. {"type": "registry", "key": "...", "value": "DisplayVersion"}
    detection_rule: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    vendor: Mapped["SoftwareVendor"] = relationship(back_populates="products")
    patches: Mapped[list["Patch"]] = relationship(back_populates="product")

    __table_args__ = (
        Index("uq_product_vendor_slug", "vendor_id", "slug", unique=True),
    )


class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("software_products.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version: Mapped[str | None] = mapped_column(String(64))
    patch_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # security | critical | important | optional | os_cumulative | custom
    severity: Mapped[str | None] = mapped_column(String(16))
    # critical | high | medium | low | info
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cve_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    kb_article: Mapped[str | None] = mapped_column(String(64))
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    delta_patch_path: Mapped[str | None] = mapped_column(Text)
    delta_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_reboot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rollback_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    product: Mapped["SoftwareProduct"] = relationship(back_populates="patches")

    __table_args__ = (
        Index("idx_patches_product", "product_id"),
        Index("idx_patches_type", "patch_type"),
        Index("idx_patches_active", "is_active"),
    )
