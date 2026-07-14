"""add structured application feedback

Revision ID: 20260714_0010
Revises: 20260714_0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0010"
down_revision = "20260714_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("job_application_pipeline")}
    columns = [
        sa.Column("feedback_type", sa.String(length=30), nullable=True),
        sa.Column("feedback_score", sa.Integer(), nullable=True),
        sa.Column("feedback_tags", sa.JSON(), nullable=True),
        sa.Column("feedback_note", sa.Text(), nullable=True),
        sa.Column("feedback_at", sa.DateTime(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("job_application_pipeline", column)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("job_application_pipeline")}
    for name in ("feedback_at", "feedback_note", "feedback_tags", "feedback_score", "feedback_type"):
        if name in existing:
            op.drop_column("job_application_pipeline", name)
