"""add persistent operational alerts

Revision ID: 20260714_0011
Revises: 20260714_0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0011"
down_revision = "20260714_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 基线 0001 用 Base.metadata.create_all 建表（含当前全部模型），
    # 全新库升级时本表已存在，需幂等处理（与 0007 同一模式）。
    if sa.inspect(op.get_bind()).has_table("operational_alert"):
        return

    op.create_table(
        "operational_alert",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("alert_key", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("alert_key", name="uq_operational_alert_alert_key"),
    )
    op.create_index("ix_operational_alert_severity", "operational_alert", ["severity"])
    op.create_index("ix_operational_alert_status", "operational_alert", ["status"])
    op.create_index("ix_operational_alert_last_seen_at", "operational_alert", ["last_seen_at"])
    op.create_index("ix_operational_alert_resolved_at", "operational_alert", ["resolved_at"])


def downgrade() -> None:
    op.drop_table("operational_alert")
