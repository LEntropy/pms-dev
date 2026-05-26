"""Add policy and deployment tables

Revision ID: 004
Revises: 003
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("patch_types", postgresql.ARRAY(sa.String), nullable=False, server_default='{"security","critical"}'),
        sa.Column("auto_install", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("install_window", postgresql.JSONB, nullable=True),
        sa.Column("max_concurrent", sa.Integer, nullable=False, server_default="10"),
        sa.Column("bandwidth_limit_kbps", sa.Integer, nullable=True),
        sa.Column("pre_install_script", sa.Text, nullable=True),
        sa.Column("post_install_script", sa.Text, nullable=True),
        sa.Column("exception_patch_ids", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("rollback_on_failure", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "policy_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patch_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patches.id"), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "deployments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("patch_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("patches.id"), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("policies.id"), nullable=True),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("total_targets", sa.Integer, nullable=True),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_deployments_status", "deployments", ["status"])
    op.create_index("idx_deployments_patch", "deployments", ["patch_id"])

    op.create_table(
        "deployment_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("endpoints.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("download_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("install_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_snapshot_id", sa.Text, nullable=True),
    )
    op.create_index("idx_dr_deployment", "deployment_results", ["deployment_id"])
    op.create_index("idx_dr_endpoint", "deployment_results", ["endpoint_id"])
    op.create_index("idx_dr_status", "deployment_results", ["status"])


def downgrade() -> None:
    op.drop_index("idx_dr_status", "deployment_results")
    op.drop_index("idx_dr_endpoint", "deployment_results")
    op.drop_index("idx_dr_deployment", "deployment_results")
    op.drop_table("deployment_results")
    op.drop_index("idx_deployments_patch", "deployments")
    op.drop_index("idx_deployments_status", "deployments")
    op.drop_table("deployments")
    op.drop_table("policy_exceptions")
    op.drop_table("policies")
