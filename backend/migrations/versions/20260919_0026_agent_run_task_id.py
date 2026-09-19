"""C1: link an agent_run to the orchestration task that owns it.

Node records (``agent_message``) only exist under an ``agent_run``, but the task
center has always been keyed by ``agent_task``. The join between the two used to
be a string convention — ``AgentRun.user_request == f"task:{id}"`` — that no
writer ever produced, so per-task token/cost lookups matched zero rows forever.
This column makes that relationship an actual foreign key.

Revision ID: 20260919_0026
Revises: 20260919_0025
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_0026"
down_revision = "20260919_0025"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_column("agent_run", "task_id"):
        return
    op.add_column("agent_run", sa.Column("task_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_agent_run_task_id", "agent_run", ["task_id"])


def downgrade() -> None:
    if not _has_column("agent_run", "task_id"):
        return
    op.drop_index("ix_agent_run_task_id", table_name="agent_run")
    op.drop_column("agent_run", "task_id")
