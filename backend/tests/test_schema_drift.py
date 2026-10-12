"""schema 只该有一条权威路径，另一条只是体检（E17）。

`app/core/schema_bootstrap.py`（453 行手写 MySQL DDL、启动时悄悄补库）已删。这里钉住三件事：
1. `describe_drift` 对两条建库路径都报"无漂移"，并且**在人为缺表/缺列时必须点名**（否则"零漂移"
   可能只是它什么都看不见）；
2. `app/**` 里不许再有手写 DDL 字符串——第四条路径不能换个文件名回来；
3. **D222**：差异的两个方向要拿到不同的等级和话术。库里**少**东西才该喊"跑 alembic upgrade head"，
   库里**多**东西喊这句只会让人白跑一次迁移（本仓开发库正好是多出来的那一侧，见模块 docstring）。
"""

from __future__ import annotations

import ast
import logging
import os
import pathlib
import subprocess
import sys

from sqlalchemy import Column, MetaData, Table, create_engine, text

import app.models  # noqa: F401  —— 不 import 模型，Base.metadata 只是子集
from app.core.database import Base
from app.core.schema_drift import EXTRA, MISSING, Drift, describe_drift, log_drift

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DDL_PREFIXES = ("ALTER TABLE", "CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX", "DROP COLUMN")


def _alembic_url(tmp_path: pathlib.Path) -> str:
    db = tmp_path / "migrated.sqlite3"
    url = f"sqlite:///{db.as_posix()}"
    env = dict(os.environ)
    env.update({"DATABASE_URL": url, "AUTO_CREATE_TABLES": "false", "PYTHONPATH": str(BACKEND)})
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(BACKEND),
        env=env,
        check=True,
        capture_output=True,
        timeout=300,
    )
    return url


def test_migrated_database_has_no_drift(tmp_path):
    engine = create_engine(_alembic_url(tmp_path))
    try:
        assert describe_drift(engine) == []
    finally:
        engine.dispose()


def test_create_all_database_has_no_drift(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'orm.sqlite3').as_posix()}")
    try:
        Base.metadata.create_all(bind=engine)
        assert describe_drift(engine) == []
    finally:
        engine.dispose()


def test_drift_names_a_missing_table(tmp_path):
    """只建一张表，其余全都"缺"——必须点名缺表，且不能把已有那张也报成缺。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'partial.sqlite3').as_posix()}")
    one = next(iter(Base.metadata.tables.values()))
    try:
        Base.metadata.create_all(bind=engine, tables=[one])
        found = describe_drift(engine)
        missing_tables = [d for d in found if d.kind == MISSING and d.text.startswith("缺表")]
        assert missing_tables, f"只建了一张表却报不出缺表：{found[:3]}"
        assert not any(one.name in d.text for d in missing_tables)
    finally:
        engine.dispose()


def test_drift_names_a_missing_column(tmp_path):
    """非空转的关键一条：少一列必须被点名成那一列，而不是"缺表"或干脆看不见。"""
    target = Base.metadata.tables["tb_user"]
    thin = MetaData()
    # 同名表、少一列。`Column.copy()` 在 SQLAlchemy 2.0 已弃用，这里显式重建所需属性即可。
    kept = [
        Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable)
        for c in target.columns
        if c.name != "role"
    ]
    Table(target.name, thin, *kept)  # noqa: F841

    engine = create_engine(f"sqlite:///{(tmp_path / 'thin.sqlite3').as_posix()}")
    try:
        thin.create_all(bind=engine)
        found = describe_drift(engine, Base.metadata)
        assert any(
            d.kind == MISSING and d.text.startswith(f"{target.name} 缺列") and "role" in d.text for d in found
        ), found
    finally:
        engine.dispose()


# ------------------------------------------------------------------- D222：两个方向分开说


def _logged(tmp_path, caplog, prepare):
    """造一个库形状（`prepare` 负责），跑 `log_drift`，返回按等级分好组的日志文本。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'drift.sqlite3').as_posix()}")
    caplog.set_level(logging.INFO, logger="app.core.schema_drift")
    try:
        prepare(engine)
        log_drift(engine)
    finally:
        engine.dispose()
    by_level: dict[str, list[str]] = {}
    for record in caplog.records:
        if record.name == "app.core.schema_drift":
            by_level.setdefault(record.levelname, []).append(record.getMessage())
    return by_level


def _prepare_missing_table(engine):
    one = next(iter(Base.metadata.tables.values()))
    Base.metadata.create_all(bind=engine, tables=[one])


def _prepare_extra_table(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE d222_stray_table (id INTEGER)"))


def test_a_missing_table_warns_and_names_the_remedy(tmp_path, caplog):
    """缺东西才是告警，而且要给出跑得动的动作：升级迁移。"""
    by_level = _logged(tmp_path, caplog, _prepare_missing_table)

    warnings = [m for m in by_level.get("WARNING", []) if m.startswith("schema 漂移：缺表")]
    assert warnings, f"缺表没被报成 WARNING：{by_level}"
    assert all("alembic upgrade head" in m for m in warnings), warnings[:2]


def test_an_extra_table_is_info_and_must_not_blame_the_migration(tmp_path, caplog):
    """这条就是 D222 的全部理由：库里多出一张模型没有的表时，喊"跑 alembic upgrade head"
    是一句让人白跑的提示——升级不会删掉任何东西。

    反向证据：把等级或话术退回成"一锅端"（都 WARNING、都说请运行），这一条先红。
    """
    by_level = _logged(tmp_path, caplog, _prepare_extra_table)

    extra_lines = [m for level, msgs in by_level.items() for m in msgs if "d222_stray_table" in m]
    assert extra_lines, f"多出来的表根本没被报出来：{by_level}"
    assert "INFO" in by_level and any("d222_stray_table" in m for m in by_level["INFO"]), by_level
    assert not any(
        "d222_stray_table" in m for m in by_level.get("WARNING", [])
    ), f"多出来的东西不该是 WARNING，因为它删不掉：{by_level.get('WARNING')}"
    assert not any("请运行" in m for m in extra_lines), f"多出来的那一侧还在喊跑迁移：{extra_lines}"


def test_describe_drift_reports_kind_not_just_text(tmp_path):
    """`kind` 是这条判据的承重件：话术（`text`）随时会改，判断不能靠读文案字符串。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'kinds.sqlite3').as_posix()}")
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE d222_stray_two (id INTEGER)"))
        found = describe_drift(engine)
        assert all(isinstance(d, Drift) for d in found), found[:2]
        stray = [d for d in found if "d222_stray_two" in d.text]
        assert [d.kind for d in stray] == [EXTRA], stray
    finally:
        engine.dispose()


def test_log_drift_survives_an_unreachable_database(tmp_path):
    """体检不能变成新的启动期故障源：库连不上时返回空，不抛穿 lifespan。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'no-such-dir' / 'x.sqlite3').as_posix()}")
    assert log_drift(engine) == []
    engine.dispose()


def _ddl_literals(source: str) -> list[str]:
    """只查字符串常量里的 DDL，且跳过 docstring——否则这段说明文字自己就会被判违规。"""
    tree = ast.parse(source)
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                doc_nodes.add(id(body[0].value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_nodes:
            text = node.value.strip().upper()
            if text.startswith(DDL_PREFIXES):
                found.append(node.value.strip()[:60])
    return found


def test_no_handwritten_ddl_inside_app():
    violations = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        hits = _ddl_literals(path.read_text(encoding="utf-8"))
        if hits:
            violations.append(f"{path.relative_to(BACKEND)}: {hits}")
    assert violations == [], "手写 DDL 只能住在 migrations/ 里，别在 app/ 里开第四条建表路径：" + "; ".join(violations)


def test_the_ddl_checker_actually_fires():
    """反方向：把旧写法喂给它，必须抓到（不然上面那条"零违规"是空的）。"""
    src = '''
from sqlalchemy import text


def ensure_x(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE job_bookmark (
                id BIGINT AUTO_INCREMENT PRIMARY KEY
            )
        """))
        conn.execute(text("ALTER TABLE tb_user ADD COLUMN role VARCHAR(20)"))
'''
    assert len(_ddl_literals(src)) == 2
