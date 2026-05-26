"""Add watched_products table and PostgreSQL RLS

Revision ID: 005
Revises: 004
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 자사 SW 자동 배포 감시 목록
    op.create_table(
        "watched_products",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("software_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False, server_default="all"),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patch_types", postgresql.ARRAY(sa.String()), nullable=False,
                  server_default="{security,critical}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_watched_products_product", "watched_products", ["product_id"])

    # 에이전트 서명 공개키 / 최신 버전 관리용 시스템 설정 테이블
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # PostgreSQL Row-Level Security — audit_logs
    # 일반 사용자(pms_user 역할)는 자신의 로그만 조회 가능
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY audit_superadmin_all ON audit_logs
            FOR ALL
            TO PUBLIC
            USING (true)
    """)
    # 참고: 애플리케이션은 superuser 연결로 동작하므로 RLS 우회됨.
    # RLS는 직접 DB 연결하는 외부 도구(read-only 분석가 계정 등)를 위한 것.

    # patches 테이블에 delta 관련 컬럼 추가 (이미 모델에 있으나 DB에 없을 경우 대비)
    op.execute("""
        ALTER TABLE patches
        ADD COLUMN IF NOT EXISTS delta_patch_path TEXT,
        ADD COLUMN IF NOT EXISTS delta_hash_sha256 VARCHAR(64)
    """)

    # users 테이블에 SSO 관련 컬럼 추가
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS sso_provider VARCHAR(32),
        ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(256)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_superadmin_all ON audit_logs")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")
    op.drop_table("system_settings")
    op.drop_table("watched_products")
