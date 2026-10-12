"""启动时把"库的实际形状"和"模型声明的形状"对一次，只报告，不动库。

这里以前住的是另一件事：`schema_bootstrap.py`，453 行、18 处 MySQL 方言手写 DDL，在每次
启动时悄悄 `ALTER TABLE ... ADD COLUMN` / `CREATE TABLE`。那等于**第四条改表路径**（Alembic、
`create_all`、散落脚本之外的一条），有两个实测到的毛病：

1. 它补的东西全是冗余：在 `alembic upgrade head` 建出来的库上，14 个 `ensure_*` 一条 DDL 都不发；
   那 6 张"要建表"的表在 `Base.metadata` 里都有模型，`create_all` 本来就会建。
2. 它是写死的 MySQL 方言，所以在 SQLite 上直接抛语法错（探针里 6 个全部炸在
   `near "KEY"/"INDEX"/"ON": syntax error`）——也就是说这条"兼容老库"的路径只对一种引擎成立，
   却在所有引擎的启动路径上。

改成漂移报告之后，"老库没迁移"从一件被悄悄兜住的事变成一条看得见的话，
而生产（`AUTO_CREATE_TABLES=false`，compose 里有专门的 `alembic upgrade head` 服务）第一次有了
"你忘了迁移"的启动期提示，而不是等到第一条查询报 no such column。

**D222：话术要分方向。** 报告刚上线时把每一条差异都写成"请运行 `alembic upgrade head`"，
可差异有两个相反的方向：库里**少**东西（那是没迁移，升级能补）和库里**多**东西
（升级不会去掉任何东西——这条提示只会让人白跑一次迁移）。本仓的开发库正好落在后一半：
比模型多出 4 张表和 1 个列，是历史上企业侧代码出树时故意留下的 schema。2026-10-12 那次
真浏览器验证里，这同一句提示把人（我）误导成"有表没建、要去跑迁移"，而 `alembic current`
其实已经在 head——所以这不是文案洁癖，是一条会让人做出错动作的提示。
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import MetaData

logger = logging.getLogger(__name__)

# Alembic 自己的版本表，模型里当然没有它——不排掉的话每条 migrated 库都会被报成漂移。
ALWAYS_IGNORED_TABLES = frozenset({"alembic_version"})

# 差异的两个方向。`missing` 是"库该有而没有"，`extra` 是"库有而模型不声明"。
MISSING = "missing"
EXTRA = "extra"


class Drift(NamedTuple):
    kind: str
    text: str


def describe_drift(engine: Engine, metadata: MetaData | None = None) -> list[Drift]:
    """返回模型与真实库之间的差异；空列表 = 两边一致。

    调用方拿 `kind` 决定等级与补救话术，别去猜 `text` 长什么样——文案改了，判断就会悄悄失效。
    """
    if metadata is None:
        from app.core.database import Base

        metadata = Base.metadata

    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names()) - ALWAYS_IGNORED_TABLES
    model_tables = set(metadata.tables)
    found: list[Drift] = []

    for name in sorted(model_tables - live_tables):
        found.append(Drift(MISSING, f"缺表 {name}"))
    for name in sorted(live_tables - model_tables):
        found.append(Drift(EXTRA, f"多出一张模型里没有的表 {name}"))

    for name in sorted(model_tables & live_tables):
        model_cols = {c.name for c in metadata.tables[name].columns}
        live_cols = {c["name"] for c in inspector.get_columns(name)}
        missing = sorted(model_cols - live_cols)
        extra = sorted(live_cols - model_cols)
        if missing:
            found.append(Drift(MISSING, f"{name} 缺列 {', '.join(missing)}"))
        if extra:
            found.append(Drift(EXTRA, f"{name} 多出模型里没有的列 {', '.join(extra)}"))
    return found


def log_drift(engine: Engine, metadata: MetaData | None = None) -> list[str]:
    """启动期用：库连不上不该拖垮进程，所以这里吞掉连接类异常并如实报出来。

    返回的是差异文本列表（保持报告刚上线时的返回值不变，调用方只用来数条数）。
    """
    try:
        found = describe_drift(engine, metadata)
    except Exception as exc:
        logger.warning("schema 漂移检查未能执行（引擎不可用？）：%s: %s", type(exc).__name__, exc)
        return []
    for drift in found:
        if drift.kind == MISSING:
            logger.warning(
                "schema 漂移：%s —— 库里缺东西，请运行 `alembic upgrade head`（或开 AUTO_CREATE_TABLES）", drift.text
            )
        else:
            # 多出来的那部分升级删不掉，也没有模型声明它；本仓的开发库就是这个状态，
            # 所以它是信息不是告警。真要清，得单独拍一次刀，而不是每次启动喊一遍。
            logger.info(
                "schema 形状差异：%s —— 库里比模型多，`alembic upgrade head` 不会去掉它；"
                "要删需要单独决定（历史上企业侧代码出树时留下的表/列就是这种状态）",
                drift.text,
            )
    return [drift.text for drift in found]
