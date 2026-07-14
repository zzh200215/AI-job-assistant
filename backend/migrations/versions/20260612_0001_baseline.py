"""baseline schema from SQLAlchemy models

Revision ID: 20260612_0001
Revises:
Create Date: 2026-06-12 00:00:00
"""

from __future__ import annotations

from alembic import op

import app.models  # noqa: F401
from app.core.database import Base

revision = "20260612_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
