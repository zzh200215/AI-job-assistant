"""job data source sync fields

Revision ID: 20260711_0005
Revises: 20260628_0004
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260711_0005"
down_revision = "20260628_0004"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _has_column("job_data_source", "next_sync_at"):
        op.add_column("job_data_source", sa.Column("next_sync_at", sa.DateTime(), nullable=True))
    if not _has_column("job_data_source", "sync_lock_at"):
        op.add_column("job_data_source", sa.Column("sync_lock_at", sa.DateTime(), nullable=True))
    if not _has_column("job_data_source", "fail_count"):
        op.add_column("job_data_source", sa.Column("fail_count", sa.Integer(), nullable=True, server_default="0"))
    if not _has_column("job_data_source", "last_error_msg"):
        op.add_column("job_data_source", sa.Column("last_error_msg", sa.Text(), nullable=True))

    try:
        op.create_index("ix_job_data_source_next_sync_at", "job_data_source", ["next_sync_at"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_job_data_source_sync_lock_at", "job_data_source", ["sync_lock_at"], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    for index_name in ["ix_job_data_source_sync_lock_at", "ix_job_data_source_next_sync_at"]:
        try:
            op.drop_index(index_name, table_name="job_data_source")
        except Exception:
            pass
    for column_name in ["last_error_msg", "fail_count", "sync_lock_at", "next_sync_at"]:
        if _has_column("job_data_source", column_name):
            try:
                op.drop_column("job_data_source", column_name)
            except Exception:
                pass
