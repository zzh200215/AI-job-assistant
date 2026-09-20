"""add editable resume workspace metadata

Revision ID: 20260714_0008
Revises: 20260714_0007
Create Date: 2026-07-14
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20260714_0008"
down_revision = "20260714_0007"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name) and any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    columns = {
        "label": sa.Column("label", sa.String(length=120), nullable=True),
        "target_jd_id": sa.Column("target_jd_id", sa.BigInteger(), nullable=True),
        "parent_version_id": sa.Column("parent_version_id", sa.BigInteger(), nullable=True),
        "change_log": sa.Column("change_log", sa.JSON(), nullable=True),
        "suggestion_decisions": sa.Column("suggestion_decisions", sa.JSON(), nullable=True),
        "ats_snapshot": sa.Column("ats_snapshot", sa.JSON(), nullable=True),
    }
    for name, column in columns.items():
        if not _has_column("resume_version", name):
            op.add_column("resume_version", column)

    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes("resume_version")}
    if "ix_resume_version_target_jd_id" not in existing_indexes:
        op.create_index("ix_resume_version_target_jd_id", "resume_version", ["target_jd_id"])
    if "ix_resume_version_parent_version_id" not in existing_indexes:
        op.create_index("ix_resume_version_parent_version_id", "resume_version", ["parent_version_id"])


def downgrade() -> None:
    with contextlib.suppress(Exception):
        op.drop_index("ix_resume_version_parent_version_id", table_name="resume_version")
    with contextlib.suppress(Exception):
        op.drop_index("ix_resume_version_target_jd_id", table_name="resume_version")
    for name in ("ats_snapshot", "suggestion_decisions", "change_log", "parent_version_id", "target_jd_id", "label"):
        if _has_column("resume_version", name):
            op.drop_column("resume_version", name)
