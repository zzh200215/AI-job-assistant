"""add AI release governance records

Revision ID: 20260714_0012
Revises: 20260714_0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0012"
down_revision = "20260714_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 基线 0001 用 Base.metadata.create_all 建表，全新库升级时本表已存在，需幂等处理。
    if sa.inspect(op.get_bind()).has_table("ai_release"):
        return

    op.create_table(
        "ai_release",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("release_key", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_versions", sa.JSON(), nullable=False),
        sa.Column("evaluation_reports", sa.JSON(), nullable=False),
        sa.Column("gate_result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("release_key", name="uq_ai_release_release_key"),
    )
    op.create_index("ix_ai_release_status", "ai_release", ["status"])
    op.create_index("ix_ai_release_created_at", "ai_release", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_release")
