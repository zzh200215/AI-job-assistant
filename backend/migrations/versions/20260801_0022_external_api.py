"""M6 external API tables: api_keys / api_usage / api_pricing / api_bill / webhook_subscriptions

对外能力 API（T6-1/2/3）新增 5 张表：
- api_keys：外部调用 Key（只存 sha256 哈希，明文仅创建时返回一次）
- api_usage：每次调用记录（限流 + 计费数据源）
- api_pricing：端点 × 单价（分/次），初始值对齐 docs/定价表.md §7
- api_bill：月度聚合账单（幂等 upsert，同周期重跑覆盖）
- webhook_subscriptions：Webhook 事件订阅

幂等说明：基线 0001 用 Base.metadata.create_all 按当前模型建全量表，全量列/索引守卫。

Revision ID: 20260801_0022
Revises: 20260801_0021
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0022"
down_revision = "20260801_0021"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("daily_quota", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
        op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])

    if not _has_table("api_usage"):
        op.create_table(
            "api_usage",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("api_key_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("endpoint", sa.String(80), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="success"),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("request_id", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_api_usage_api_key_id", "api_usage", ["api_key_id"])
        op.create_index("ix_api_usage_tenant_id", "api_usage", ["tenant_id"])
        op.create_index("ix_api_usage_created_at", "api_usage", ["created_at"])
        op.create_index("ix_api_usage_request_id", "api_usage", ["request_id"])

    if not _has_table("api_pricing"):
        op.create_table(
            "api_pricing",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("endpoint", sa.String(80), nullable=False, unique=True),
            sa.Column("unit_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_api_pricing_endpoint", "api_pricing", ["endpoint"])
        op.execute(
            "INSERT INTO api_pricing (endpoint, unit_price, is_active, created_at, updated_at) VALUES "
            "('resume.parse', 30, 1, NOW(), NOW()), "
            "('match.evaluate', 30, 1, NOW(), NOW()), "
            "('interview.simulate', 80, 1, NOW(), NOW())"
        )

    if not _has_table("api_bill"):
        op.create_table(
            "api_bill",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("api_key_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("period_start", sa.DateTime(), nullable=False),
            sa.Column("period_end", sa.DateTime(), nullable=False),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("line_items", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_api_bill_api_key_id", "api_bill", ["api_key_id"])
        op.create_index("ix_api_bill_tenant_id", "api_bill", ["tenant_id"])

    if not _has_table("webhook_subscriptions"):
        op.create_table(
            "webhook_subscriptions",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("api_key_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("event", sa.String(80), nullable=False),
            sa.Column("url", sa.String(500), nullable=False),
            sa.Column("secret", sa.String(64), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_webhook_subscriptions_api_key_id", "webhook_subscriptions", ["api_key_id"])
        op.create_index("ix_webhook_subscriptions_tenant_id", "webhook_subscriptions", ["tenant_id"])


def downgrade() -> None:
    for table in [
        "webhook_subscriptions",
        "api_bill",
        "api_pricing",
        "api_usage",
        "api_keys",
    ]:
        if _has_table(table):
            op.drop_table(table)
