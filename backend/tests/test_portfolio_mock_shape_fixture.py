"""反向守卫：`frontend/tests/fixtures/portfolioReportShape*.json` 没过期。

前端那一页的守卫读这两份夹具（三个项目与四个项目），所以夹具一旦落后于后端真输出，
红的是这条——而不是让前端对着一个"曾经对过"的形状继续画。比对两侧共用同一个 `payload_for`，
两边不是两套想象。**两份**是必须的：只钉 N=3 时，"2~N 泛化"这一档在页面那棵树里只验过一个点。
"""

from __future__ import annotations

import json

import pytest

from app.models.portfolio_report_job import STAGE_QUESTIONS, PortfolioReportJob
from app.services import portfolio_report_job_service as jobs
from scripts.collect_mock_portfolio_report_shape import COMBOS, normalize, payload_for
from tests.portfolio_report_payloads import PARSED


@pytest.mark.parametrize(
    "indices,parsed,out",
    COMBOS,
    ids=[f"{len(picked)}个项目" for picked, _parsed, _out in COMBOS],
)
def test_前端夹具与后端真输出逐字相同(db_session, indices, parsed, out):
    current = normalize(payload_for(db_session, list(indices), parsed))
    committed = json.loads(out.read_text(encoding="utf-8"))
    assert committed == current, (
        f"前端夹具（{out.name}）与后端真输出不一致：改过 mock 载荷、组合六维表或装配函数之后要重跑 "
        "backend/scripts/collect_mock_portfolio_report_shape.py 并提交新的夹具。"
    )


def test_父行只有三大节而第四节只住在子行那一格里(db_session):
    """一份文档只有一个出处：两处都能写的那一份迟早长得不一样。"""
    normalize(payload_for(db_session, [0, 1, 2], PARSED))
    parent = db_session.query(PortfolioReportJob).filter(PortfolioReportJob.stage == "report").one()
    child = db_session.query(PortfolioReportJob).filter(PortfolioReportJob.stage == STAGE_QUESTIONS).one()

    assert parent.report_json["questions"] is None
    assert parent.report_json["questions_state"] == "not_generated"
    assert set(child.report_json) == {"questions", "distribution", "practice", "deferred", "excluded"}
    assert child.parent_job_id == parent.id
    # 组合那一族的键与单项目那一族同一条：勾的是同一批项目，不是另一份简历。
    assert child.combo_key == parent.combo_key == "0,1,2"
    assert child.project_indices == parent.project_indices

    assembled = jobs.assemble_document(db_session, parent)
    assert assembled["questions"]["distribution"]["total"] == 12
    assert assembled["questions_state"] == "ready"
    assert assembled["questions"]["practice"]["must_practice"] == child.report_json["practice"]["must_practice"]
