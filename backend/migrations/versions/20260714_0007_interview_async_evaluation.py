"""add persistent interview turn evaluations and memory state

Revision ID: 20260714_0007
Revises: 20260712_0006
Create Date: 2026-07-14
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20260714_0007"
down_revision = "20260712_0006"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name) and any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    if not _has_column("interview_session", "evaluation_status"):
        op.add_column(
            "interview_session",
            sa.Column("evaluation_status", sa.String(length=20), nullable=False, server_default="idle"),
        )
    if not _has_column("interview_session", "memory_snapshot"):
        op.add_column("interview_session", sa.Column("memory_snapshot", sa.JSON(), nullable=True))

    if sa.inspect(op.get_bind()).has_table("interview_turn_evaluation"):
        return

    op.create_table(
        "interview_turn_evaluation",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.BigInteger(), sa.ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("turn_id", sa.String(length=80), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True, server_default="general"),
        sa.Column("user_answer", sa.Text(), nullable=True),
        sa.Column("is_follow_up", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("completeness", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expression", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("improvement", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("error_msg", sa.String(length=500), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("session_id", "turn_id", name="uq_interview_turn_evaluation_turn"),
    )
    op.create_index("ix_interview_turn_evaluation_session_id", "interview_turn_evaluation", ["session_id"])
    op.create_index("ix_interview_turn_evaluation_status", "interview_turn_evaluation", ["status"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("interview_turn_evaluation"):
        with contextlib.suppress(Exception):
            op.drop_index("ix_interview_turn_evaluation_status", table_name="interview_turn_evaluation")
        with contextlib.suppress(Exception):
            op.drop_index("ix_interview_turn_evaluation_session_id", table_name="interview_turn_evaluation")
        op.drop_table("interview_turn_evaluation")
    if _has_column("interview_session", "memory_snapshot"):
        op.drop_column("interview_session", "memory_snapshot")
    if _has_column("interview_session", "evaluation_status"):
        op.drop_column("interview_session", "evaluation_status")
