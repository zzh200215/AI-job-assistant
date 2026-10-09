"""D178: give the interview turn-evaluation claim a lease so one row can only be claimed once.

`_claim_status` used to hand out a claim purely on `status`, and `status` has two legal
transitions (`pending→running`, `running→pending`). Two replicas sweeping the same stale row
could therefore each take a claim — measured on real MySQL with 8 processes on 2026-10-09
(D177): rowcounts came back `1 0 0 1 0 0 0 0`, both callers submitted, and the same question
was paid for twice. A timestamp of *who took it when* is what makes the claim exclusive per
row rather than per transition.

Revision ID: 20260919_0027
Revises: 20260919_0026
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_0027"
down_revision = "20260919_0026"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_column("interview_turn_evaluation", "claimed_at"):
        return
    op.add_column("interview_turn_evaluation", sa.Column("claimed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if not _has_column("interview_turn_evaluation", "claimed_at"):
        return
    op.drop_column("interview_turn_evaluation", "claimed_at")
