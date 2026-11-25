"""Guard the repair migration for the report-job id primary keys.

The original migrations declared autoincrement without primary_key, so a fresh
MySQL database creates an unwritable table. Removing the repair migration, or
dropping one of the three tables from its list, would silently bring the bug back.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND / "migrations" / "versions"
REPAIR = "20261120_0034_report_job_primary_key.py"
TABLES = ("resume_report_job", "project_report_job", "portfolio_report_job")


def test_repair_migration_is_the_head_and_covers_all_report_job_tables():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head == "20261120_0034", "修复迁移不在链头，alembic upgrade head 不会执行它"

    source = (MIGRATIONS / REPAIR).read_text(encoding="utf-8")
    assert "ADD PRIMARY KEY (id)" in source
    assert "AUTO_INCREMENT" in source
    for table in TABLES:
        assert f'"{table}"' in source, f"修复迁移没有覆盖 {table}"
