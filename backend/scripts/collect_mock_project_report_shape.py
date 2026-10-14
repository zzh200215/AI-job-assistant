"""导出"mock 世界里一份完整的单项目分析长什么样"到前端守卫用的夹具：
`frontend/tests/fixtures/projectReportShape.json`。

为什么要有这个文件：与 `collect_mock_report_shape.py` 同一条理由——这一族也有**两种渲染**
（后端自包含 HTML 与前端那一页 Vue），各自读同一份装配出来的文档。后端这一侧有交付前机检，
前端那一侧若只靠手搓夹具，"后端换了个键名"这类漂移就是**画少了但不报错**。
这个夹具把两棵树钉在一起：前端守卫逐节比对上屏，后端
`tests/test_mock_project_report_shape_fixture.py` 反向盯着夹具没过期。

跑法（在 `backend/` 下）：`./.venv/Scripts/python.exe scripts/collect_mock_project_report_shape.py`
改动了 mock 载荷、六维表、装配函数或候选人视图之后要重跑一次，否则反向守卫会红。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 必须先设环境变量再 import config：本机 `.env` 写的是真 provider，而这份夹具的定义就是
# "不打补丁的 mock 派发能长出什么"。
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
from app.models.project_report_job import STAGE_QUESTIONS, ProjectReportJob  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import llm_service  # noqa: E402
from app.services import project_report_job_service as jobs  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "projectReportShape.json"


@compiles(BigInteger, "sqlite")
def _big_integer_as_integer(_type, _compiler, **_kwargs):
    """与根 `conftest.py` 同一条钩子：SQLite 只有 `INTEGER PRIMARY KEY` 才是 rowid 别名。"""
    return "INTEGER"


def normalize(payload: dict) -> dict:
    """抹掉每次跑都会变的那几位：三个自增主键、两个时刻与报告日期。"""
    out = dict(payload)
    out["job_id"] = 1
    out["questions_job_id"] = 2
    out["resume_id"] = 1
    out["create_time"] = "2026-01-01T00:00:00"
    out["finished_at"] = "2026-01-01T00:00:01"
    doc = {**out["report"], "report_date": "2026-01-01", "resume_id": 1, "job_id": 1, "questions_job_id": 2}
    out["report"] = doc
    return out


def payload_for(db) -> dict:
    """在**给定会话**上跑一遍真派发（前三节 + 第四节各一行），返回轮询载荷的字节。"""
    user = User(
        username="mock_project_shape",
        email="mock_project_shape@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()

    resume = Resume(
        name="张三",
        file_name="mock.pdf",
        file_path="uploads/mock.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=llm_service._MOCK_RESUME,
    )
    db.add(resume)
    db.commit()

    job = jobs.create_project_report_job(
        db,
        user_id=user.id,
        resume_id=resume.id,
        project_index=0,
        project_name="智能简历解析服务",
        jd_id=None,
        target_position="",
    )
    assert jobs.run_job_on(db, job.id) is True
    db.expire_all()
    parent = db.get(ProjectReportJob, job.id)
    assert parent.status == "completed", parent.error_msg
    assert parent.excluded == 0

    child = jobs.create_questions_job(db, parent=parent)
    assert jobs.run_job_on(db, child.id) is True
    db.expire_all()
    child = db.get(ProjectReportJob, child.id)
    assert child.status == "completed" and child.stage == STAGE_QUESTIONS, child.error_msg

    row = db.get(ProjectReportJob, parent.id)
    assert {stage: item["source"] for stage, item in (row.provenance_json or {}).items()} == {
        "profile": "mock",
        "diagrams": "mock",
        "advice": "mock",
    }, row.provenance_json
    assert (row.errors_json or {}).get("stage_errors", {}) == {}, row.errors_json
    return normalize(resume_api.get_project_report_job_api(row.id, db=db, current_user=user)["data"])


def main() -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        payload = payload_for(db)
    finally:
        db.close()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")

    doc = payload["report"]
    print(f"已写 {OUT.name}（{len(text.encode('utf-8')) / 1024:.1f} KB）")
    print(f"  六维合计 {doc['score_cell']} / 评级 {doc['grade']} / 难度 {doc['difficulty']['level']}")
    print(f"  图 {doc['diagrams']['figures']}")
    print(
        f"  第四节 {doc['questions']['distribution']['total']} 题，需补强 {doc['questions']['distribution']['weak']}，高危 {doc['questions']['distribution']['high_risk']}"
    )
    print(
        f"  位次 第 {doc['contribution']['rank']} 个 · 系数 {doc['contribution']['coefficient']} · 占比 {doc['contribution']['share']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
