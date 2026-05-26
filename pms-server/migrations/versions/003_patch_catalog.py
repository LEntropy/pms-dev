"""Add patch catalog tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "software_vendors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
    )

    op.create_table(
        "software_products",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("software_vendors.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("detection_rule", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("uq_product_vendor_slug", "software_products", ["vendor_id", "slug"], unique=True)

    op.create_table(
        "patches",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("software_products.id"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("previous_version", sa.String(64), nullable=True),
        sa.Column("patch_type", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("cve_ids", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("kb_article", sa.String(64), nullable=True),
        sa.Column("release_date", sa.Date, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("file_hash_sha256", sa.String(64), nullable=False),
        sa.Column("delta_patch_path", sa.Text, nullable=True),
        sa.Column("delta_hash_sha256", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("requires_reboot", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("rollback_supported", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_patches_product", "patches", ["product_id"])
    op.create_index("idx_patches_type", "patches", ["patch_type"])
    op.create_index("idx_patches_active", "patches", ["is_active"])


def downgrade() -> None:
    op.drop_index("idx_patches_active", "patches")
    op.drop_index("idx_patches_type", "patches")
    op.drop_index("idx_patches_product", "patches")
    op.drop_table("patches")
    op.drop_index("uq_product_vendor_slug", "software_products")
    op.drop_table("software_products")
    op.drop_table("software_vendors")
