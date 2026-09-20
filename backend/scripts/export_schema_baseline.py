"""导出 ORM 模型对应的数据库 Schema 基线快照（T1-2 冻结数据模型基线）。

本脚本**不连接任何数据库**：从 `Base.metadata` 读取全部模型定义，
用 MySQL 8.0 方言离线编译为 DDL，输出到仓库根 `docs/schema-baseline.sql`。

用途：
  1. 冻结基线：   python scripts/export_schema_baseline.py
  2. CI 漂移检测： python scripts/export_schema_baseline.py --check
     （与已提交的 docs/schema-baseline.sql 比对，不一致则退出码 1）

变更纪律（T1-2/T1-3）：任何表结构变更必须先走 Alembic 迁移脚本
（backend/migrations/versions/），再重新导出并提交本快照。
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_mock_engine

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
SNAPSHOT_PATH = REPO_ROOT / "docs" / "schema-baseline.sql"

# 保证 `app` 包可从 backend 根目录导入（无论从何处调用本脚本）
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 注册全部模型到 Base.metadata（这两行必须在 sys.path 之后，故豁免 E402）
import app.models  # noqa: E402,F401
from app.core.database import Base  # noqa: E402

HEADER = """-- 数据库 Schema 基线快照（T1-2 冻结数据模型基线）
-- 生成方式：backend/scripts/export_schema_baseline.py（离线编译，MySQL 8.0 方言）
-- 变更纪律：任何表结构变更必须先走 Alembic 迁移（backend/migrations/versions/），
--           再重新生成本快照并连同迁移脚本一并提交；CI 会对本文件做漂移检测。
"""


def render_ddl() -> str:
    """将 Base.metadata 编译为稳定的 MySQL DDL 文本。

    - CREATE TABLE 与 CREATE INDEX 都按语句文本排序：这份快照只用于 CI 漂移检测，
      没有任何消费方按顺序执行它，而 SQLAlchemy 对"无依赖关系"的表只按注册顺序排，
      那个顺序等于 `app/models/__init__.py` 的 import 顺序——排序调整就会伪装成 schema 漂移。
    """
    statements: list[str] = []

    def executor(sql, *multiparams, **params) -> None:
        statements.append(str(sql))

    engine = create_mock_engine("mysql+pymysql://", executor=executor)
    Base.metadata.create_all(engine)

    tables = sorted(s for s in statements if s.startswith("CREATE TABLE"))
    indexes = sorted(
        s for s in statements if s.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX"))
    )
    others = [
        s for s in statements if not s.startswith("CREATE TABLE") and not s.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX"))
    ]

    ordered = tables + indexes + others
    body = "\n".join(f"{stmt};" for stmt in ordered if stmt.strip())
    return HEADER + "\n" + body + "\n"


def main() -> int:
    ddl = render_ddl()

    if "--check" in sys.argv:
        if not SNAPSHOT_PATH.exists():
            print(
                f"[schema-baseline] MISSING: {SNAPSHOT_PATH} 未提交基线快照",
                file=sys.stderr,
            )
            return 1
        if SNAPSHOT_PATH.read_text(encoding="utf-8") != ddl:
            print(
                "[schema-baseline] DRIFT DETECTED: ORM 模型与 docs/schema-baseline.sql 不一致",
                file=sys.stderr,
            )
            print(
                "[schema-baseline] 修复: python scripts/export_schema_baseline.py 并提交更新（表结构变更请先走 Alembic 迁移）",
                file=sys.stderr,
            )
            return 1
        print("[schema-baseline] OK: ORM 模型与基线快照一致")
        return 0

    SNAPSHOT_PATH.write_text(ddl, encoding="utf-8", newline="\n")
    print(f"[schema-baseline] 快照已写入: {SNAPSHOT_PATH}（{len(ddl)} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
