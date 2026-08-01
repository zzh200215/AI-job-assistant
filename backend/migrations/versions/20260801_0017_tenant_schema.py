"""tenant schema: extend organization + tenant_configs / tenant_domain_bindings

Revision ID: 20260801_0017
Revises: 20260714_0016
Create Date: 2026-08-01

T2-1 定稿「organization = 租户」：本迁移在 organization 上补租户品牌/计费字段，
并新建租户附属表 tenant_configs / tenant_domain_bindings。

幂等说明：基线 0001 用 Base.metadata.create_all 按当前模型建全量表，
全新库升级时新列/新表/新索引可能已存在（或部分存在），故全部使用
has_column / has_table / has_index 守卫（沿用 0007/0011 模式）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0017"
down_revision = "20260714_0016"
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
    inspector = sa.inspect(op.get_bind())

    # 1. organization 新增租户字段
    additions = {
        "industry": sa.Column("industry", sa.String(length=50), nullable=True),
        "logo_url": sa.Column("logo_url", sa.String(length=500), nullable=True),
        "primary_color": sa.Column("primary_color", sa.String(length=20), nullable=True),
        "plan_tier": sa.Column("plan_tier", sa.String(length=20), nullable=False, server_default="free"),
        "admin_user_id": sa.Column("admin_user_id", sa.BigInteger(), nullable=True),
        "expires_at": sa.Column("expires_at", sa.DateTime(), nullable=True),
        "isolation_mode": sa.Column("isolation_mode", sa.String(length=20), nullable=False, server_default="shared"),
    }
    for column in additions.values():
        if not _has_column("organization", column.name):
            op.add_column("organization", column)

    # 2. organization 租户索引
    for index_name, columns in (
        ("ix_organization_plan_tier", ["plan_tier"]),
        ("ix_organization_status", ["status"]),
        ("ix_organization_expires_at", ["expires_at"]),
    ):
        if not _has_index("organization", index_name):
            op.create_index(index_name, "organization", columns)

    # 3. tenant_configs / tenant_domain_bindings
    if not inspector.has_table("tenant_configs"):
        op.create_table(
            "tenant_configs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("config_key", sa.String(length=50), nullable=False),
            sa.Column("config_value", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "config_key", name="uq_tenant_configs_key"),
        )
        op.create_index("ix_tenant_configs_tenant_id", "tenant_configs", ["tenant_id"])

    if not inspector.has_table("tenant_domain_bindings"):
        op.create_table(
            "tenant_domain_bindings",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
            sa.Column("is_primary", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("domain", name="uq_tenant_domain"),
        )
        op.create_index("ix_tenant_domain_bindings_tenant_id", "tenant_domain_bindings", ["tenant_id"])

    # 4. 回填：存量租户管理员默认取 owner_id（plan_tier/isolation_mode 由 server_default 兜底）
    op.execute("UPDATE organization SET admin_user_id = owner_id WHERE admin_user_id IS NULL")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    for index_name in ("ix_organization_expires_at", "ix_organization_status", "ix_organization_plan_tier"):
        if _has_index("organization", index_name):
            op.drop_index(index_name, table_name="organization")

    for table_name in ("tenant_domain_bindings", "tenant_configs"):
        if inspector.has_table(table_name):
            op.drop_table(table_name)

    for column_name in ("industry", "logo_url", "primary_color", "plan_tier", "admin_user_id", "expires_at", "isolation_mode"):
        if _has_column("organization", column_name):
            op.drop_column("organization", column_name)
