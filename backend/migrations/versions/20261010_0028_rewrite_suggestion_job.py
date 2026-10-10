"""D200: give the rewrite-suggestion call a durable row so the HTTP request stops waiting on the LLM.

The endpoint it backs is one provider call measured at 4.58–12.08s (thinking disabled, D196) and
91.77s with an empty answer (thinking enabled, D189). Synchronously that call holds one of the 20
anyio worker threads (`core/threadpool.py` pins the ceiling to DB_POOL_SIZE + DB_MAX_OVERFLOW) for
its whole duration, and the answer has nowhere to go.

This table is *not* the resume. The candidate-facing invariant is "a suggestion never rewrites my
CV", which is about `tb_resume.parsed_json`; storing the pending payload here keeps that invariant
intact while letting the request return immediately. Nothing reads this table back into a resume.

Revision ID: 20261010_0028
Revises: 20260919_0027
Create Date: 2026-10-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261010_0028"
down_revision = "20260919_0027"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table("rewrite_suggestion_job"):
        return

    op.create_table(
        "rewrite_suggestion_job",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("jd_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("block_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suggestions", sa.JSON(), nullable=True),
        sa.Column("rejected", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("error", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_rewrite_suggestion_job_user_id", "rewrite_suggestion_job", ["user_id"])
    op.create_index("ix_rewrite_suggestion_job_resume_id", "rewrite_suggestion_job", ["resume_id"])
    op.create_index("ix_rewrite_suggestion_job_status", "rewrite_suggestion_job", ["status"])
    op.create_index("ix_rewrite_suggestion_job_create_time", "rewrite_suggestion_job", ["create_time"])


def downgrade() -> None:
    op.drop_table("rewrite_suggestion_job")
