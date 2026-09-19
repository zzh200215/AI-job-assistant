"""A4: one canonical match score per (resume version, job).

Three code paths previously produced three different numbers for the same pair
and none applied the weak-fit cap, so the recommend page and the explain page
disagreed. This table stores the single displayed score.

Revision ID: 20260919_0024
Revises: 20260919_0023
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_0024"
down_revision = "20260919_0023"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table("match_score"):
        return

    op.create_table(
        "match_score",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("resume_version", sa.String(64), nullable=False),
        sa.Column("jd_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("cap_applied", sa.Float(), nullable=True),
        sa.Column("method", sa.String(32), nullable=False, server_default="rubric_6dim"),
        sa.Column("dimensions_json", sa.Text(), nullable=True),
        sa.Column("skill_gap_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_match_score_user_id", "match_score", ["user_id"])
    op.create_index("ix_match_score_resume_id", "match_score", ["resume_id"])
    op.create_index("ix_match_score_jd_id", "match_score", ["jd_id"])
    op.create_index("ix_match_score_tenant_user", "match_score", ["tenant_id", "user_id"])
    op.create_index(
        "uq_match_score_resume_version_jd",
        "match_score",
        ["resume_id", "resume_version", "jd_id"],
        unique=True,
    )


def downgrade() -> None:
    if _has_table("match_score"):
        op.drop_table("match_score")
