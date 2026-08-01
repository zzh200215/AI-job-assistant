"""add one-time Feishu SSO states

Revision ID: 20260714_0015
Revises: 20260714_0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0015"
down_revision = "20260714_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 基线 0001 用 Base.metadata.create_all 建表，全新库升级时本表已存在，需幂等处理。
    if sa.inspect(op.get_bind()).has_table("organization_sso_state"):
        return

    op.create_table(
        "organization_sso_state",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("state_hash", name="uq_organization_sso_state_hash"),
    )
    op.create_index("ix_organization_sso_state_state_hash", "organization_sso_state", ["state_hash"])
    op.create_index("ix_organization_sso_state_organization_id", "organization_sso_state", ["organization_id"])
    op.create_index("ix_organization_sso_state_expires_at", "organization_sso_state", ["expires_at"])


def downgrade() -> None:
    op.drop_table("organization_sso_state")
