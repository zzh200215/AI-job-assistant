"""interview config tables (T3-2)

Create tenant-scoped interview configuration tables:
interview_question_bank / interview_scoring_rule / interview_report_template.
tenant_id NULL = platform default, consistent with T3-1 subscription plans.

Revision ID: 20260801_0020
Revises: 20260801_0019
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260801_0020"
down_revision = "20260801_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("interview_question_bank"):
        op.create_table(
            "interview_question_bank",
            sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
            sa.Column("type", sa.String(30), nullable=False),
            sa.Column("title", sa.String(100), nullable=False, server_default=""),
            # MySQL 不允许 TEXT/JSON 列带 DEFAULT，ORM 层 default 负责缺省值
            sa.Column("prompt_template", sa.Text(), nullable=True),
            sa.Column("questions", sa.JSON(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_interview_question_bank_tenant_id", "interview_question_bank", ["tenant_id"])
        op.create_index(
            "uq_interview_question_bank_tenant_type",
            "interview_question_bank",
            ["tenant_id", "type"],
            unique=True,
        )

    if not inspector.has_table("interview_scoring_rule"):
        op.create_table(
            "interview_scoring_rule",
            sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
            sa.Column("dimension", sa.String(30), nullable=False),
            sa.Column("label", sa.String(50), nullable=False, server_default=""),
            sa.Column("weight", sa.Numeric(5, 4), nullable=False, server_default="0.2500"),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_interview_scoring_rule_tenant_id", "interview_scoring_rule", ["tenant_id"])
        op.create_index(
            "uq_interview_scoring_rule_tenant_dim",
            "interview_scoring_rule",
            ["tenant_id", "dimension"],
            unique=True,
        )

    if not inspector.has_table("interview_report_template"):
        op.create_table(
            "interview_report_template",
            sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
            # MySQL 不允许 TEXT 列带 DEFAULT，ORM 层 default 负责缺省值
            sa.Column("template", sa.Text(), nullable=True),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_interview_report_template_tenant_id", "interview_report_template", ["tenant_id"])
        op.create_index(
            "uq_interview_report_template_tenant",
            "interview_report_template",
            ["tenant_id"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    for table in (
        "interview_question_bank",
        "interview_scoring_rule",
        "interview_report_template",
    ):
        if inspector.has_table(table):
            op.drop_table(table)
