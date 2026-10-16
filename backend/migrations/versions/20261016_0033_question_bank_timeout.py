"""D238 P1.2：给题型配置行加一列"这一题给多少秒"。

原来全场一个 30 秒写死在 `InterviewEngine.TIMEOUT_SECONDS`，唯一的消费者是
`interview_ws.py` 里那句 `asyncio.sleep`——技术题与项目题真实需要 1–3 分钟，30 秒必然判超时，
这是用户可感知的硬伤（`简历与面试优化.md` I1）。

这一列挂在 `interview_question_bank` 上，因为那张表本来就是**题型级**的配置（T3-2），
回落顺序与 `get_scoring_rules` 同形：平台配置行（`tenant_id IS NULL` 且启用）→
`interview_config_service.QUESTION_TIMEOUT_SECONDS` 的内置默认 → 认不出题型时 45 秒。

**没填这列（NULL）不是"给 0 秒"，是"这一题型按内置默认"**，所以列必须可空且服务端把
NULL/0 都当"未配置"处理——见 `timeout_for_type` 的注释。

一件事必须说在前面：本表 `type` 自己的定义与 `DEFAULT_QUESTION_BANKS` 用的是
{tech,hr,comprehensive,stress,group} 那套，而运行时题目带的是 {basic,tech,project,scenario}，
**两套只交集于 tech**。今天这表 0 行所以无冲突；真要在管理端按新列配超时，得先对齐词表，
否则配下去的行永远查不中、静默走内置默认（`TYPE_VOCABULARY_MISMATCH` 记着这件事）。

Revision ID: 20261016_0033
Revises: 20261014_0032
Create Date: 2026-10-16
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "20261016_0033"
down_revision = "20261014_0032"
branch_labels = None
depends_on = None

TABLE = "interview_question_bank"
COLUMN = "timeout_seconds"


def _has_column() -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        return False
    return COLUMN in {c["name"] for c in insp.get_columns(TABLE)}


def upgrade() -> None:
    # 幂等：快照/手工建库路径可能已经带上这列（模型里有了，create_all 就会建出来）。
    if _has_column():
        return
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            sa.Integer(),
            nullable=True,
            comment="该题型的作答秒数；NULL=回落内置默认",
        ),
    )


def downgrade() -> None:
    with contextlib.suppress(Exception):
        if _has_column():
            op.drop_column(TABLE, COLUMN)
