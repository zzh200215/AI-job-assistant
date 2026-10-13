"""D229: give a resume evaluation report a durable row.

一份六模块报告最多要跑三发模型调用（概览 / 批改稿 / 面试预演）。按 D201 量到的最坏单发
16.02s 与 D189 的 364.5s 退避上界，一条同步路由会把一根 anyio 线程 + 一条 DB 连接按住几分钟，
而且中间任何一发挂了，前面花掉的钱就全丢了。所以它和改写作业同一族形状：一行作业、租约、读时自愈。

表名与 `rewrite_suggestion_job` 分开是刻意的：两者的租约上界（45 分钟 vs 15 分钟）与保留期
（3 天 vs 7 天）不同，压成一张表就是让两个不同的东西共用一套状态机。

Revision ID: 20261013_0030
Revises: 20261012_0029
Create Date: 2026-10-13
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20261013_0030"
down_revision = "20261012_0029"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table("resume_report_job"):
        return
    op.create_table(
        "resume_report_job",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("jd_id", sa.BigInteger(), nullable=True),
        sa.Column("target_position", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("grade", sa.String(length=4), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=True),
        sa.Column("errors_json", sa.JSON(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        sa.Column("lint_failures", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_resume_report_job_user_id", "resume_report_job", ["user_id"])
    op.create_index("ix_resume_report_job_resume_id", "resume_report_job", ["resume_id"])
    op.create_index("ix_resume_report_job_status", "resume_report_job", ["status"])
    op.create_index("ix_resume_report_job_create_time", "resume_report_job", ["create_time"])


def downgrade() -> None:
    with contextlib.suppress(Exception):
        for name in ("user_id", "resume_id", "status", "create_time"):
            op.drop_index(f"ix_resume_report_job_{name}", table_name="resume_report_job")
    op.drop_table("resume_report_job")
