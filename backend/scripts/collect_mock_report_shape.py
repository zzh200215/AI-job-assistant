"""导出"mock 世界里一份完整的六模块报告长什么样"到前端守卫用的夹具：
`frontend/tests/fixtures/mockReportShape.json`。

为什么要有这个文件（D231）：六模块那条链有**两种渲染**——后端那一份自包含 HTML 和
前端那一页 Vue，它们各自读同一份 `report_json`。后端这一侧有交付前机检守着，
前端那一侧原来只有手搓的夹具，所以"后端换了个键名"这一类漂移在前端是
**画少了但不报错**（这一族踩过：漏参数→渲染 0、传错对象→整段空）。这个夹具把两棵树钉在一起：
前端守卫逐节比对上屏，后端 `tests/test_mock_report_shape_fixture.py` 反向盯着夹具没有过期。

跑法（在 `backend/` 下）：`./.venv/Scripts/python.exe scripts/collect_mock_report_shape.py`
改动了 mock 载荷、七维表或候选人视图之后要重跑一次，否则反向守卫会红。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 必须先设环境变量再 import config：本机 `.env` 写的是真 provider，而这份夹具的定义就是
# "不打补丁的 mock 派发能长出什么"。进程环境变量优先级高于 `.env`。
# `sqlite://` 而不是 `sqlite:///:memory:`：与根 conftest 同一个值，`app.core.database`
# 只对前者启用 StaticPool——所有连接共用那一个内存库，`prompt_trace` 那类后台自己开 session
# 写的表才在同一个库里。
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["REDIS_URL"] = ""
os.environ["TESTING"] = "true"
os.environ["RUN_SCHEDULER"] = "false"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

import app.models  # noqa: E402, F401  # 注册全部模型，create_all 才建得全
from app.api import resume as resume_api  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.history import Resume  # noqa: E402
from app.models.report_job import ResumeReportJob  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import llm_service  # noqa: E402
from app.services import report_job_service as jobs  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "mockReportShape.json"


@compiles(BigInteger, "sqlite")
def _big_integer_as_integer(_type, _compiler, **_kwargs):
    """与根 `conftest.py` 同一条钩子：SQLite 只有 `INTEGER PRIMARY KEY` 才是 rowid 别名（才会自增）。
    模型清一色 BigInteger 主键，钩子不挂在任何 DDL 之前，建出来的表插不进一行。"""
    return "INTEGER"


def normalize(payload: dict) -> dict:
    """抹掉每次跑都会变的四位：两个自增主键、两个时刻与报告日期。

    前端那份守卫比的是**形状与内容**，比上这些就等于让夹具跟着时钟红
    （`report_date` 取的是 `utc_now()`，跨一天就对不上）。
    反向守卫（`tests/test_mock_report_shape_fixture.py`）也先归一再比，两边同一把尺。
    """
    out = dict(payload)
    out["job_id"] = 1
    out["resume_id"] = 1
    out["create_time"] = "2026-01-01T00:00:00"
    out["finished_at"] = "2026-01-01T00:00:01"
    out["report"] = {**out["report"], "report_date": "2026-01-01", "resume_id": 1}
    return out


def payload_for(db) -> dict:
    """在**给定会话**上跑一遍真派发（不打补丁），返回 `getReportJob` 吐给前端的字节。

    会话由调用方给，是因为两个调用方要的库不一样：脚本用 app 引擎那一条内存库，
    反向守卫 `tests/test_mock_report_shape_fixture.py` 用 pytest 的事务会话（跑完回滚）。
    两边共用这一份实现，夹具才不会和后端实际输出各说各话。
    """
    user = User(
        username="mock_report_shape",
        email="mock_report_shape@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
        expected_salary_min=15,
        expected_salary_max=22,
    )
    db.add(user)
    db.commit()

    resume = Resume(
        name="示例候选人",
        file_name="mock.pdf",
        file_path="uploads/mock.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=llm_service._MOCK_RESUME,
    )
    db.add(resume)
    db.commit()

    job = jobs.create_report_job(db, user_id=user.id, resume_id=resume.id, jd_id=None, target_position="")
    assert jobs.run_job_on(db, job.id) is True
    db.expire_all()

    row = db.get(ResumeReportJob, job.id)
    assert row.status == "completed", row.error_msg
    assert {stage: item["source"] for stage, item in (row.provenance_json or {}).items()} == {
        "overview": "mock",
        "redline": "mock",
        "interview": "mock",
    }, row.provenance_json
    assert (row.errors_json or {}).get("stage_errors", {}) == {}, row.errors_json
    return normalize(resume_api.get_report_job_api(row.id, db=db, current_user=user)["data"])


def main() -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        payload = payload_for(db)
    finally:
        db.close()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")

    report = payload["report"]
    print(f"已写 {OUT.name}（{len(text.encode('utf-8')) / 1024:.1f} KB）")
    print(f"  总分 {payload['total_score']} / 等级 {payload['grade']}")
    print(
        f"  七维 {len(report['dimensions'])} 行、批改 {report['redline']['total']} 处"
        f"（关键 {report['redline']['key_total']}）"
    )
    print(
        f"  面试 {report['interview']['distribution']['total']} 题、"
        f"需补强 {report['interview']['distribution']['weak']} 题"
    )
    print(f"  投递策略 {len(report['apply_strategy']['chapters'])} 章、版面 {len(report['sections'])} 块")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
