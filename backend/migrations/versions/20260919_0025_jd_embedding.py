"""B3: persist job-posting embeddings.

Recommendation used to embed the whole active-JD table on every uncached
request, with only a 512-entry in-process LRU between calls — so a restart
re-paid the full embedding cost and a 1000-job corpus would cost 100 API
batches per refresh. This table stores one vector per (jd, provider, model)
with the text fingerprint it was computed from.

Revision ID: 20260919_0025
Revises: 20260919_0024
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_0025"
down_revision = "20260919_0024"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table("jd_embedding"):
        return

    op.create_table(
        "jd_embedding",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("jd_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("text_hash", sa.String(32), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vector", sa.Text(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jd_embedding_jd_id", "jd_embedding", ["jd_id"])
    op.create_index(
        "uq_jd_embedding_jd_provider_model",
        "jd_embedding",
        ["jd_id", "provider", "model"],
        unique=True,
    )


def downgrade() -> None:
    if _has_table("jd_embedding"):
        op.drop_table("jd_embedding")
