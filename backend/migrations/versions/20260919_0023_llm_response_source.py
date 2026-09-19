"""A1: record the actual provenance of every LLM response.

`prompt_trace.provider` stores the *configured* provider, so a response served by
the mock fallback chain was previously logged as `provider=qwen`. These two
columns make the effective source queryable:

- response_source: real | mock | truncated | fallback_model | unknown
- degraded: 1 when the response is not from the configured primary model

Revision ID: 20260919_0023
Revises: 20260801_0022
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_0023"
down_revision = "20260801_0022"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("prompt_trace", "response_source"):
        op.add_column(
            "prompt_trace",
            sa.Column("response_source", sa.String(20), nullable=False, server_default="unknown"),
        )
        op.create_index("ix_prompt_trace_response_source", "prompt_trace", ["response_source"])
    if not _has_column("prompt_trace", "degraded"):
        op.add_column(
            "prompt_trace",
            sa.Column("degraded", sa.SmallInteger(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("prompt_trace", "degraded"):
        op.drop_column("prompt_trace", "degraded")
    if _has_column("prompt_trace", "response_source"):
        op.drop_index("ix_prompt_trace_response_source", table_name="prompt_trace")
        op.drop_column("prompt_trace", "response_source")
