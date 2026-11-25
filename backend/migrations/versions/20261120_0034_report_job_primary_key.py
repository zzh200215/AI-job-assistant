"""Repair report-job tables whose id column was created without a primary key.

The 20261013/20261014 migrations declared `autoincrement=True` but forgot
`primary_key=True`, so MySQL created `resume_report_job.id` (and the project /
portfolio siblings on a fresh migration run) as a plain BIGINT. Inserts then
fail with "Field 'id' doesn't have a default value".

This migration is idempotent: it only alters a table whose id is not already
an auto-increment primary key. SQLite tests create the tables from ORM
metadata, so the repair is intentionally a no-op outside MySQL.

Revision ID: 20261120_0034
Revises: 20261016_0033
Create Date: 2026-11-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261120_0034"
down_revision = "20261016_0033"
branch_labels = None
depends_on = None

REPORT_JOB_TABLES = ("resume_report_job", "project_report_job", "portfolio_report_job")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    inspector = sa.inspect(bind)
    for table in REPORT_JOB_TABLES:
        if not inspector.has_table(table):
            continue
        pk_columns = inspector.get_pk_constraint(table).get("constrained_columns") or []
        id_column = next((col for col in inspector.get_columns(table) if col["name"] == "id"), None)
        if id_column is None:
            continue
        if pk_columns == ["id"] and id_column.get("autoincrement") is True:
            continue
        if pk_columns and pk_columns != ["id"]:
            continue
        if pk_columns:
            op.execute(f"ALTER TABLE `{table}` MODIFY id BIGINT NOT NULL AUTO_INCREMENT")
        else:
            op.execute(f"ALTER TABLE `{table}` MODIFY id BIGINT NOT NULL AUTO_INCREMENT, ADD PRIMARY KEY (id)")


def downgrade() -> None:
    # Reverting would recreate a table that cannot accept inserts; keep the repair.
    pass
