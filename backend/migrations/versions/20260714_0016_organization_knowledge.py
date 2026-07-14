"""scope knowledge documents to organizations

Revision ID: 20260714_0016
Revises: 20260714_0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260714_0016"
down_revision = "20260714_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("kb_document")}
    if "organization_id" not in columns:
        op.add_column("kb_document", sa.Column("organization_id", sa.BigInteger(), nullable=True))
        op.create_index("ix_kb_document_organization_id", "kb_document", ["organization_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("kb_document")}
    if "organization_id" in columns:
        op.drop_index("ix_kb_document_organization_id", table_name="kb_document")
        op.drop_column("kb_document", "organization_id")
