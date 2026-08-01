"""T1-2 数据模型基线：schema 快照一致性测试。

验证：
1. docs/schema-baseline.sql 存在且已提交；
2. ORM 模型与快照一致（任何模型改动未同步快照即失败——要求先走 Alembic 迁移）；
3. DDL 渲染确定性（重复生成结果一致，保证 CI diff 稳定）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.export_schema_baseline import SNAPSHOT_PATH, render_ddl  # noqa: E402


def test_snapshot_file_exists():
    assert SNAPSHOT_PATH.exists(), "缺少 docs/schema-baseline.sql（T1-2 基线快照未提交）"


def test_snapshot_matches_models():
    current = render_ddl()
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert committed == current, (
        "ORM 模型与 docs/schema-baseline.sql 不一致：表结构变更必须先走 "
        "Alembic 迁移（backend/migrations/versions/），再执行 "
        "python scripts/export_schema_baseline.py 重新生成并提交快照。"
    )


def test_render_is_deterministic():
    assert render_ddl() == render_ddl(), "DDL 渲染不稳定，检查脚本排序逻辑"
