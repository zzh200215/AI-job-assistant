"""agent message llm usage columns

Revision ID: 20260624_0003
Revises: 20260616_0002
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260624_0003"
down_revision = "20260616_0002"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _has_column("agent_message", "tokens_used"):
        op.add_column("agent_message", sa.Column("tokens_used", sa.Integer(), nullable=True, server_default="0"))
    if not _has_column("agent_message", "cost_cents"):
        op.add_column("agent_message", sa.Column("cost_cents", sa.Float(), nullable=True, server_default="0"))


def downgrade() -> None:
    if _has_column("agent_message", "cost_cents"):
        op.drop_column("agent_message", "cost_cents")
    if _has_column("agent_message", "tokens_used"):
        op.drop_column("agent_message", "tokens_used")
