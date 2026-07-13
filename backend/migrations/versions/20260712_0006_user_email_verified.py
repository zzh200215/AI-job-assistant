"""add user email verification status

Revision ID: 20260712_0006
Revises: 20260711_0005
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260712_0006"
down_revision = "20260711_0005"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("tb_user", "email_verified"):
        op.add_column(
            "tb_user",
            sa.Column("email_verified", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("tb_user", "email_verified"):
        op.drop_column("tb_user", "email_verified")
