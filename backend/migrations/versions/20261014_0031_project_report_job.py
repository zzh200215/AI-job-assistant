"""D235: 给"一个项目"的分析一行可恢复的作业。

量程与 `resume_report_job` 不同：那一行是一份简历的六模块，这一行是**一个项目**的四大节，
而且第四节是按按钮才跑的第二次调用——所以多两列：`project_index`（位次那一维与占比都由它算）
与 `stage` + `parent_job_id`（questions 行指回它续跑的那一份 report 行）。
租约与保留期沿用同一组设置（`REPORT_JOB_*`），因为这里的每一发与那里是同一个 provider、
同一个上界（D201 量到的最坏单发 16.02s、D189 的 364.5s 退避上界）。

文档只存父行那一份：questions 行只存自己那一节，读与下载都走同一个装配函数，
一份文档有两个副本迟早长得不一样。

Revision ID: 20261014_0031
Revises: 20261013_0030
Create Date: 2026-10-14
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20261014_0031"
down_revision = "20261013_0030"
branch_labels = None
depends_on = None

TABLE = "project_report_job"


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
        sa.Column("project_index", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(length=200), nullable=True),
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
    for name in ("user_id", "resume_id", "stage", "status", "parent_job_id", "create_time"):
        op.create_index(f"ix_{TABLE}_{name}", TABLE, [name])


def downgrade() -> None:
    with contextlib.suppress(Exception):
        for name in ("user_id", "resume_id", "stage", "status", "parent_job_id", "create_time"):
            op.drop_index(f"ix_{TABLE}_{name}", table_name=TABLE)
    op.drop_table(TABLE)
