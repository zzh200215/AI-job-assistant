"""task center control fields

Revision ID: 20260616_0002
Revises: 20260612_0001
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260616_0002"
down_revision = "20260612_0001"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _has_column("agent_task", "strategy_name"):
        op.add_column("agent_task", sa.Column("strategy_name", sa.String(length=50), nullable=True))
    if not _has_column("agent_task", "retry_of_task_id"):
        op.add_column("agent_task", sa.Column("retry_of_task_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    if _has_column("agent_task", "retry_of_task_id"):
        op.drop_column("agent_task", "retry_of_task_id")
    if _has_column("agent_task", "strategy_name"):
        op.drop_column("agent_task", "strategy_name")
