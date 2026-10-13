"""反向守卫：前端那份 `mockReportShape.json` 还是后端现在长出来的样子吗。

两条腿的形状与 `validationShapes.json` 那一对同源（D116）：
* 前端腿逐节比对上屏（`frontend/tests/unit/resumeReportMockShape.test.js`）；
* 这一条腿盯着夹具本身没过期。

少了这一条腿会怎样：后端改了键名、改了 mock 载荷或改了七维表，前端那份守卫仍拿着旧夹具全绿，
而真页面上少画一节且不报错——这一族在抽取搬家的账上记过三次。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.collect_mock_report_shape import OUT, normalize, payload_for


def test_committed_fixture_is_what_the_backend_emits_now(db_session):
    """跑的是真派发，所以这一条同时也是"mock 下六节能齐"的一次复述。"""
    fresh = payload_for(db_session)
    committed = json.loads(Path(OUT).read_text(encoding="utf-8"))

    assert committed == fresh, (
        "前端夹具与后端当前输出不一致：在 backend/ 下重跑 "
        "`./.venv/Scripts/python.exe scripts/collect_mock_report_shape.py` 再提交。"
    )


def test_the_fixture_carries_every_module_the_page_draws(db_session):
    """夹具的承重字段：前端那一页逐条读这些，少一个就是画少了而不报错。

    这一条与上一条分工不同——上一条比全文，这一条只点名"哪些键是页面要的"，
    所以它红的时候能说清是哪一族漂移。
    """
    committed = json.loads(Path(OUT).read_text(encoding="utf-8"))
    report = committed["report"]

    for key in ("verdict", "dimensions", "total_score", "grade", "grade_desc", "grade_scale", "to_next_grade"):
        assert key in report, key
    assert len(report["dimensions"]) == 7
    assert {row["key"] for row in report["dimensions"]} == {
        "metric_ownership",
        "interview_hooks",
        "role_fit",
        "transferability",
        "project_depth",
        "expression_structure",
        "advantage_section",
    }
    assert set(report["redline"]) >= {"blocks", "total", "key_total", "mode", "stat"}
    assert set(report["interview"]) >= {"deferred", "questions", "distribution"}
    assert set(report["apply_strategy"]) >= {"source", "chapters"}
    assert set(report["personalization"]) == {"one_line_label", "opener"}
    # 候选人视图里不该有对内证据，这是下载与轮询共用的那条口径。
    for forbidden in ("model_reported_total", "provenance", "stage_errors", "redline_rejected"):
        assert forbidden not in json.dumps(report, ensure_ascii=False), forbidden
    # 归一化之后不该留任何随时钟变化的值：留了这条就会每天红一次。
    assert normalize(committed) == committed
