"""D237: 给"几个项目叠在一起"的组合分析一行可恢复的作业。

与 `project_report_job` 的区别只有一个但很硬：那一行按**一个项目**建，
这一行按**一组项目**建，所以键是 `combo_key`（选中了简历里哪几个项目的规范化序号，
顺序无关、重复去掉），外加 `project_indices` 与 `project_count` 两列把这一组是什么存下来。
租约、保留期、线程池沿用同一组 `REPORT_JOB_*` 设置——同一个 provider、同一个上界。

文档只存父行那一份：questions 行只存自己那一节，读与下载都走同一个装配函数。

Revision ID: 20261014_0032
Revises: 20261014_0031
Create Date: 2026-10-14
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20261014_0032"
down_revision = "20261014_0031"
branch_labels = None
depends_on = None

TABLE = "portfolio_report_job"
INDEXED = ("user_id", "resume_id", "combo_key", "stage", "status", "parent_job_id", "create_time")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("combo_key", sa.String(length=64), nullable=False),
        sa.Column("project_indices", sa.JSON(), nullable=False),
        sa.Column("project_count", sa.Integer(), nullable=False),
        sa.Column("project_names", sa.JSON(), nullable=True),
        sa.Column("stage", sa.String(length=16), nullable=False, server_default="report"),
        sa.Column("parent_job_id", sa.BigInteger(), nullable=True),
        sa.Column("jd_id", sa.BigInteger(), nullable=True),
        sa.Column("target_position", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("grade", sa.String(length=8), nullable=True),
        sa.Column("difficulty", sa.String(length=4), nullable=True),
        sa.Column("excluded", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.Column("errors_json", sa.JSON(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        sa.Column("lint_failures", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
    )
    for name in INDEXED:
        op.create_index(f"ix_{TABLE}_{name}", TABLE, [name])


def downgrade() -> None:
    with contextlib.suppress(Exception):
        for name in INDEXED:
            op.drop_index(f"ix_{TABLE}_{name}", table_name=TABLE)
    op.drop_table(TABLE)
