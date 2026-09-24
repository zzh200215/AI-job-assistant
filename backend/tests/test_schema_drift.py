"""schema 只该有一条权威路径，另一条只是体检（E17）。

`app/core/schema_bootstrap.py`（453 行手写 MySQL DDL、启动时悄悄补库）已删。这里钉住两件事：
1. `describe_drift` 对两条建库路径都报"无漂移"，并且**在人为缺表/缺列时必须点名**（否则"零漂移"
   可能只是它什么都看不见）；
2. `app/**` 里不许再有手写 DDL 字符串——第四条路径不能换个文件名回来。
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

from sqlalchemy import Column, MetaData, Table, create_engine

import app.models  # noqa: F401  —— 不 import 模型，Base.metadata 只是子集
from app.core.database import Base
from app.core.schema_drift import describe_drift, log_drift

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
        lines = describe_drift(engine)
        missing_tables = [x for x in lines if x.startswith("缺表")]
        assert missing_tables, f"只建了一张表却报不出缺表：{lines[:3]}"
        assert not any(one.name in x for x in missing_tables)
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
        lines = describe_drift(engine, Base.metadata)
        assert any(line.startswith(f"{target.name} 缺列") and "role" in line for line in lines), lines
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
