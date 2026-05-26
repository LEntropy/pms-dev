"""Initial schema - Phase 1

Revision ID: 001
Revises:
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("ad_ou_dn", sa.Text, nullable=True),
        sa.Column("hr_dept_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("mfa_secret", sa.String(255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # endpoint_groups
    op.create_table(
        "endpoint_groups",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("membership_rule", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # endpoints
    op.create_table(
        "endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("fqdn", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("mac_address", sa.String(17), nullable=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("os_name", sa.String(128), nullable=True),
        sa.Column("os_version", sa.String(64), nullable=True),
        sa.Column("os_build", sa.String(64), nullable=True),
        sa.Column("arch", sa.String(16), nullable=True),
        sa.Column("agent_version", sa.String(32), nullable=True),
        sa.Column("agent_token", sa.Text, unique=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("endpoint_groups.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("idx_endpoints_org", "endpoints", ["organization_id"])
    op.create_index("idx_endpoints_status", "endpoints", ["status"])
    op.create_index("idx_endpoints_last_seen", "endpoints", ["last_seen_at"])

    # endpoint_group_members
    op.create_table(
        "endpoint_group_members",
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("endpoints.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("endpoint_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(64), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_audit_actor", "audit_logs", ["actor_id", "occurred_at"])
    op.create_index("idx_audit_resource", "audit_logs", ["resource", "resource_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("endpoint_group_members")
    op.drop_index("idx_endpoints_last_seen", "endpoints")
    op.drop_index("idx_endpoints_status", "endpoints")
    op.drop_index("idx_endpoints_org", "endpoints")
    op.drop_table("endpoints")
    op.drop_table("endpoint_groups")
    op.drop_table("users")
    op.drop_table("organizations")
