"""D226: give a batch JD import a durable row, so the request stops holding a worker thread.

Measured on this machine (D219, same work: parse + one ORM object per row + commit):
50 rows = 20 ms, 300 rows = 99 ms, **2000 rows = 677 ms** — and the 10 MB upload limit means the
denominator is file size, not luck. Before this the route ran in a worker thread (D219) so it no
longer froze the event loop, but it still occupied one of the 20 anyio threads *and* one DB
connection for the whole import, with nothing to show the candidate except a spinner.

The table's name deliberately avoids `job_import_batch` / `job_sync_log`: those exist in databases
older than the enterprise-side removal, but the migrations that created them left with it — D223
measured that a fresh `alembic upgrade head` produces neither. Reusing an orphan name would both
collide on old databases and be unbuildable on new ones.

Revision ID: 20261012_0029
Revises: 20261010_0028
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261012_0029"
down_revision = "20261010_0028"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table("job_import_task"):
        return

    op.create_table(
        "job_import_task",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="imported"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("problems", sa.JSON(), nullable=True),
        sa.Column("error", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_job_import_task_user_id", "job_import_task", ["user_id"])
    op.create_index("ix_job_import_task_status", "job_import_task", ["status"])
    op.create_index("ix_job_import_task_create_time", "job_import_task", ["create_time"])


def downgrade() -> None:
    op.drop_table("job_import_task")
