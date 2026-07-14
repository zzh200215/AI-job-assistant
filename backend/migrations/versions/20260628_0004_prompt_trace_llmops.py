"""prompt trace llmops fields

Revision ID: 20260628_0004
Revises: 20260624_0003
Create Date: 2026-06-28
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20260628_0004"
down_revision = "20260624_0003"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _has_column("prompt_trace", "prompt_family"):
        op.add_column("prompt_trace", sa.Column("prompt_family", sa.String(length=50), nullable=True))
        op.create_index("ix_prompt_trace_prompt_family", "prompt_trace", ["prompt_family"], unique=False)
    if not _has_column("prompt_trace", "prompt_name"):
        op.add_column("prompt_trace", sa.Column("prompt_name", sa.String(length=100), nullable=True))
        op.create_index("ix_prompt_trace_prompt_name", "prompt_trace", ["prompt_name"], unique=False)
    if not _has_column("prompt_trace", "trace_context"):
        op.add_column("prompt_trace", sa.Column("trace_context", sa.JSON(), nullable=True))
    if not _has_column("prompt_trace", "prompt_metadata"):
        op.add_column("prompt_trace", sa.Column("prompt_metadata", sa.JSON(), nullable=True))
    if not _has_column("prompt_trace", "feedback_label"):
        op.add_column("prompt_trace", sa.Column("feedback_label", sa.String(length=50), nullable=True))
        op.create_index("ix_prompt_trace_feedback_label", "prompt_trace", ["feedback_label"], unique=False)
    if not _has_column("prompt_trace", "feedback_note"):
        op.add_column("prompt_trace", sa.Column("feedback_note", sa.Text(), nullable=True))
    if not _has_column("prompt_trace", "feedback_score"):
        op.add_column("prompt_trace", sa.Column("feedback_score", sa.Float(), nullable=True))


def downgrade() -> None:
    for index_name in [
        "ix_prompt_trace_feedback_label",
        "ix_prompt_trace_prompt_name",
        "ix_prompt_trace_prompt_family",
    ]:
        with contextlib.suppress(Exception):
            op.drop_index(index_name, table_name="prompt_trace")
    for column_name in [
        "feedback_score",
        "feedback_note",
        "feedback_label",
        "prompt_metadata",
        "trace_context",
        "prompt_name",
        "prompt_family",
    ]:
        if _has_column("prompt_trace", column_name):
            op.drop_column("prompt_trace", column_name)
