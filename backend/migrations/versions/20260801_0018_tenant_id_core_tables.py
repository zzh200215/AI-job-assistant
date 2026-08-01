"""tenant_id on core business tables (T2-4)

Revision ID: 20260801_0018
Revises: 20260801_0017
Create Date: 2026-08-01

首批业务表接入租户隔离（T2-4）：9 张核心表新增 tenant_id（默认内置租户 1），
复合索引 (tenant_id, user_id)，存量数据回填 tenant_id=1。

幂等说明：基线 0001 用 Base.metadata.create_all 按当前模型建全量表，
全新库升级时新列/新索引可能已存在，全部使用 has_column / has_index 守卫。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0018"
down_revision = "20260801_0017"
branch_labels = None
depends_on = None

# 表名 -> 复合索引名（与模型 TenantScopedMixin + __table_args__ 保持一致）
_TABLES = (
    ("tb_resume", "ix_tb_resume_tenant_user"),
    ("tb_analysis_record", "ix_tb_analysis_record_tenant_user"),
    ("interview_session", "ix_interview_session_tenant_user"),
    ("job_application_pipeline", "ix_job_application_pipeline_tenant_user"),
    ("job_recommend_feedback", "ix_job_recommend_feedback_tenant_user"),
    ("job_bookmark", "ix_job_bookmark_tenant_user"),
    ("subscription_order", "ix_subscription_order_tenant_user"),
    ("user_subscription", "ix_user_subscription_tenant_user"),
    ("audit_log", "ix_audit_log_tenant_user"),
)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    for table_name, index_name in _TABLES:
        if not _has_column(table_name, "tenant_id"):
            op.add_column(
                table_name,
                sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            )
        if not _has_index(table_name, index_name):
            op.create_index(index_name, table_name, ["tenant_id", "user_id"])
        # 存量数据回填默认租户（T2-4 数据迁移：单租户存量归属内置租户 1）
        op.execute(f"UPDATE {table_name} SET tenant_id = 1 WHERE tenant_id IS NULL")


def downgrade() -> None:
    for table_name, index_name in reversed(_TABLES):
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "tenant_id"):
            op.drop_column(table_name, "tenant_id")
