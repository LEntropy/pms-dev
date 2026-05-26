"""Add endpoint_software table

Revision ID: 002
Revises: 001
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "endpoint_software",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("install_path", sa.Text, nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_ep_sw_endpoint", "endpoint_software", ["endpoint_id"])
    op.create_unique_constraint(
        "uq_endpoint_software", "endpoint_software", ["endpoint_id", "raw_name"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_endpoint_software", "endpoint_software")
    op.drop_index("idx_ep_sw_endpoint", "endpoint_software")
    op.drop_table("endpoint_software")
