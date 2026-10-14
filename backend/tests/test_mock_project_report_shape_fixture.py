"""反向守卫：`frontend/tests/fixtures/projectReportShape.json` 没过期。

前端那一页的守卫读这份夹具，所以夹具一旦落后于后端真输出，红的是这条——
而不是让前端对着一个"曾经对过"的形状继续画。比对两侧共用同一个 `payload_for`，
两边不是两套想象。
"""

from __future__ import annotations

import json

from app.models.project_report_job import STAGE_QUESTIONS, ProjectReportJob
from app.services import project_report_job_service as jobs
from scripts.collect_mock_project_report_shape import OUT, normalize, payload_for


def test_the_frontend_fixture_matches_a_live_mock_run(db_session):
    current = normalize(payload_for(db_session))
    committed = json.loads(OUT.read_text(encoding="utf-8"))
    assert committed == current, (
        "前端夹具与后端真输出不一致：改过 mock 载荷、六维表或装配函数之后要重跑 "
        "backend/scripts/collect_mock_project_report_shape.py 并提交新的夹具。"
    )


def test_the_parent_row_holds_the_document_and_the_child_only_the_fourth_section(db_session):
    """一份文档只有一个出处：父行的三大节里没有 questions，第四节只住在子行那一格里。

    这条钉的是"别处不能再写一份第四节"——两个都能写的那份文档迟早长得不一样。
    """
    normalize(payload_for(db_session))
    parent = db_session.query(ProjectReportJob).filter(ProjectReportJob.stage == "report").one()
    child = db_session.query(ProjectReportJob).filter(ProjectReportJob.stage == STAGE_QUESTIONS).one()

    assert parent.report_json["questions"] is None
    assert parent.report_json["questions_state"] == "not_generated"
    assert set(child.report_json) == {"questions", "distribution", "practice", "deferred", "excluded"}
    assert child.parent_job_id == parent.id

    assembled = jobs.assemble_document(db_session, parent)
    assert assembled["questions"]["distribution"]["total"] == 8
    assert assembled["questions_state"] == "ready"
    assert assembled["advice"]["practice"]["high_risk"] == child.report_json["practice"]["high_risk"]
