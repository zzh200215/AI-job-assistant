"""add organization tenancy foundation

Revision ID: 20260714_0013
Revises: 20260714_0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0013"
down_revision = "20260714_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("tb_user")}
    if "active_organization_id" not in user_columns:
        op.add_column("tb_user", sa.Column("active_organization_id", sa.BigInteger(), nullable=True))

    # 基线 0001 用 Base.metadata.create_all 建表，全新库升级时本表已存在，需幂等处理。
    if not inspector.has_table("organization"):
        op.create_table(
            "organization",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("owner_id", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_organization_slug"),
        )
        op.create_index("ix_organization_owner_id", "organization", ["owner_id"])
        op.create_index("ix_organization_slug", "organization", ["slug"])

    if not inspector.has_table("organization_membership"):
        op.create_table(
            "organization_membership",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_membership_user"),
        )
        op.create_index("ix_organization_membership_organization_id", "organization_membership", ["organization_id"])
        op.create_index("ix_organization_membership_user_id", "organization_membership", ["user_id"])


def downgrade() -> None:
    op.drop_table("organization_membership")
    op.drop_table("organization")
    inspector = sa.inspect(op.get_bind())
    if "active_organization_id" in {column["name"] for column in inspector.get_columns("tb_user")}:
        op.drop_column("tb_user", "active_organization_id")
