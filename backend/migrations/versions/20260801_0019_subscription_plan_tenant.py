"""subscription_plan: tenant-scoped custom plans (T3-1)

Add tenant_id (NULL = platform default) and is_custom to subscription_plan;
replace the tier unique key with a (tenant_id, tier) composite unique index
so tenants can override plan name/price without touching platform defaults.

Revision ID: 20260801_0019
Revises: 20260801_0018
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0019"
down_revision = "20260801_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("subscription_plan")}
    indexes = {index["name"] for index in inspector.get_indexes("subscription_plan")}

    # 用 batch 模式替换直接 ALTER：
    # SQLite 的列级 UNIQUE（tier）实现为 sqlite_autoindex_*，对 get_indexes/get_unique_constraints
    # 完全不可见，直接 drop_index("tier") 永远匹配不到 → 旧 tier 唯一约束残留，
    # 升级后插入第二条同 tier 行（租户自定义套餐）会撞 IntegrityError。
    # batch_alter_table 在 SQLite 上重建表，反射不到的列级 UNIQUE 会被自然丢弃。
    with op.batch_alter_table("subscription_plan") as batch_op:
        if "tenant_id" not in columns:
            batch_op.add_column(
                sa.Column("tenant_id", sa.BigInteger(), nullable=True, comment="归属租户 organization.id；NULL=平台默认套餐")
            )
            batch_op.create_index("ix_subscription_plan_tenant_id", ["tenant_id"])
        if "is_custom" not in columns:
            batch_op.add_column(
                sa.Column("is_custom", sa.Integer(), nullable=False, server_default="0", comment="是否租户自定义套餐")
            )

        # tier 全局唯一 → (tenant_id, tier) 联合唯一（tenant_id NULL 表示平台默认行）
        if "tier" in indexes:
            batch_op.drop_index("tier")
        if "uq_subscription_plan_tenant_tier" not in indexes:
            batch_op.create_unique_constraint(
                "uq_subscription_plan_tenant_tier",
                ["tenant_id", "tier"],
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("subscription_plan")}
    indexes = {index["name"] for index in inspector.get_indexes("subscription_plan")}

    with op.batch_alter_table("subscription_plan") as batch_op:
        if "uq_subscription_plan_tenant_tier" in indexes:
            batch_op.drop_constraint("uq_subscription_plan_tenant_tier", type_="unique")
        if "tier" not in indexes:
            batch_op.create_index("tier", ["tier"], unique=True)

    if "tenant_id" in columns:
        op.drop_index("ix_subscription_plan_tenant_id", table_name="subscription_plan")
        op.drop_column("subscription_plan", "tenant_id")
    if "is_custom" in columns:
        op.drop_column("subscription_plan", "is_custom")
