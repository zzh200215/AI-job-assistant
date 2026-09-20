"""track resume versions used for job applications

Revision ID: 20260714_0009
Revises: 20260714_0008
Create Date: 2026-07-14
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20260714_0009"
down_revision = "20260714_0008"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name) and any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    if not _has_column("job_application_pipeline", "resume_version_id"):
        op.add_column("job_application_pipeline", sa.Column("resume_version_id", sa.BigInteger(), nullable=True))
    if not _has_column("job_application_pipeline", "resume_version_label"):
        op.add_column(
            "job_application_pipeline", sa.Column("resume_version_label", sa.String(length=120), nullable=True)
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("job_application_pipeline")}
    if "ix_job_application_pipeline_resume_version_id" not in indexes:
        op.create_index(
            "ix_job_application_pipeline_resume_version_id",
            "job_application_pipeline",
            ["resume_version_id"],
        )


def downgrade() -> None:
    with contextlib.suppress(Exception):
        op.drop_index("ix_job_application_pipeline_resume_version_id", table_name="job_application_pipeline")
    if _has_column("job_application_pipeline", "resume_version_label"):
        op.drop_column("job_application_pipeline", "resume_version_label")
    if _has_column("job_application_pipeline", "resume_version_id"):
        op.drop_column("job_application_pipeline", "resume_version_id")
