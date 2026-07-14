"""add Feishu SSO identity mapping

Revision ID: 20260714_0014
Revises: 20260714_0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0014"
down_revision = "20260714_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("organization")}
    if "sso_provider" not in columns:
        op.add_column("organization", sa.Column("sso_provider", sa.String(length=20), nullable=True))
    op.create_table(
        "organization_sso_identity",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "provider", "subject", name="uq_organization_sso_subject"),
    )
    op.create_index("ix_organization_sso_identity_organization_id", "organization_sso_identity", ["organization_id"])
    op.create_index("ix_organization_sso_identity_user_id", "organization_sso_identity", ["user_id"])


def downgrade() -> None:
    op.drop_table("organization_sso_identity")
    inspector = sa.inspect(op.get_bind())
    if "sso_provider" in {column["name"] for column in inspector.get_columns("organization")}:
        op.drop_column("organization", "sso_provider")
