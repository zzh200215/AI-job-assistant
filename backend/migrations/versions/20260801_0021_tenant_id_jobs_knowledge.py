"""tenant_id on tb_jd and kb_document (T3-3)

岗位库与知识库接入租户隔离（T3-3）：tb_jd / kb_document 新增 tenant_id（NULL=平台共享）。
存量数据回填规则：
- 平台共享数据（user_id / organization_id 均为空）保持 tenant_id=NULL，对所有租户可见；
- 用户自建岗位 / 个人知识文档回填内置默认租户 1（user 维度可见性不依赖 tenant_id）；
- 组织工作区知识文档回填对应组织（tenant_id = organization_id，Organization 即租户）。

与模型保持一致：tb_jd 复合索引 (tenant_id, is_active)；kb_document 单列索引 tenant_id。
幂等说明：基线 0001 用 Base.metadata.create_all 按当前模型建全量表，全量列/索引守卫。

Revision ID: 20260801_0021
Revises: 20260801_0020
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0021"
down_revision = "20260801_0020"
branch_labels = None
depends_on = None


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
    # ---- tb_jd：岗位库 ----
    if not _has_column("tb_jd", "tenant_id"):
        op.add_column("tb_jd", sa.Column("tenant_id", sa.BigInteger(), nullable=True))
    if not _has_index("tb_jd", "ix_tb_jd_tenant_active"):
        op.create_index("ix_tb_jd_tenant_active", "tb_jd", ["tenant_id", "is_active"])
    # 用户自建岗位归属默认租户；平台共享岗位（user_id 为空）保持 NULL
    op.execute("UPDATE tb_jd SET tenant_id = 1 WHERE tenant_id IS NULL AND user_id IS NOT NULL")

    # ---- kb_document：知识库 ----
    if not _has_column("kb_document", "tenant_id"):
        op.add_column("kb_document", sa.Column("tenant_id", sa.BigInteger(), nullable=True))
    if not _has_index("kb_document", "ix_kb_document_tenant_id"):
        op.create_index("ix_kb_document_tenant_id", "kb_document", ["tenant_id"])
    # 组织工作区文档归属对应组织（tenant = organization）；个人文档归属默认租户；平台共享保持 NULL
    op.execute(
        "UPDATE kb_document SET tenant_id = organization_id " "WHERE tenant_id IS NULL AND organization_id IS NOT NULL"
    )
    op.execute(
        "UPDATE kb_document SET tenant_id = 1 "
        "WHERE tenant_id IS NULL AND organization_id IS NULL AND user_id IS NOT NULL"
    )


def downgrade() -> None:
    if _has_index("tb_jd", "ix_tb_jd_tenant_active"):
        op.drop_index("ix_tb_jd_tenant_active", table_name="tb_jd")
    if _has_column("tb_jd", "tenant_id"):
        op.drop_column("tb_jd", "tenant_id")
    if _has_index("kb_document", "ix_kb_document_tenant_id"):
        op.drop_index("ix_kb_document_tenant_id", table_name="kb_document")
    if _has_column("kb_document", "tenant_id"):
        op.drop_column("kb_document", "tenant_id")
