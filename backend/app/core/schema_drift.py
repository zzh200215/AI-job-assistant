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
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import MetaData

logger = logging.getLogger(__name__)

# Alembic 自己的版本表，模型里当然没有它——不排掉的话每条 migrated 库都会被报成漂移。
ALWAYS_IGNORED_TABLES = frozenset({"alembic_version"})


def describe_drift(engine: Engine, metadata: MetaData | None = None) -> list[str]:
    """返回模型与真实库之间的差异描述；空列表 = 两边一致。"""
    if metadata is None:
        from app.core.database import Base

        metadata = Base.metadata

    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names()) - ALWAYS_IGNORED_TABLES
    model_tables = set(metadata.tables)
    lines: list[str] = []

    for name in sorted(model_tables - live_tables):
        lines.append(f"缺表 {name}")
    for name in sorted(live_tables - model_tables):
        lines.append(f"多出一张模型里没有的表 {name}")

    for name in sorted(model_tables & live_tables):
        model_cols = {c.name for c in metadata.tables[name].columns}
        live_cols = {c["name"] for c in inspector.get_columns(name)}
        missing = sorted(model_cols - live_cols)
        extra = sorted(live_cols - model_cols)
        if missing:
            lines.append(f"{name} 缺列 {', '.join(missing)}")
        if extra:
            lines.append(f"{name} 多出模型里没有的列 {', '.join(extra)}")
    return lines


def log_drift(engine: Engine, metadata: MetaData | None = None) -> list[str]:
    """启动期用：库连不上不该拖垮进程，所以这里吞掉连接类异常并如实报出来。"""
    try:
        lines = describe_drift(engine, metadata)
    except Exception as exc:
        logger.warning("schema 漂移检查未能执行（引擎不可用？）：%s: %s", type(exc).__name__, exc)
        return []
    for line in lines:
        logger.warning("schema 漂移：%s —— 请运行 `alembic upgrade head`（或开 AUTO_CREATE_TABLES）", line)
    return lines
