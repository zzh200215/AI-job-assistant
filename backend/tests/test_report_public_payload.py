"""三份报告"对内证据不上屏"的判据（D17）。

起因是一次**我自己写错的怀疑**：我说作品集/项目的作业载荷里带着 `stage_errors`（里面可能有
`RuntimeError: …`），会随响应进候选人浏览器。查完发现不是——三个 schema 各有 `_INTERNAL_KEYS`，
`to_public_dict()` 把它们滤掉，落库写的就是这一份；`stage_errors` 另存 `errors_json`，而轮询载荷
从不返回 `errors_json`。所以这里没有缺陷，但**证据很薄**：

* 已有的判据只有简历那一份，而且手写五个键名（`test_resume_report_service.py` 里那一条）；
* 项目/作品集那两份没有任何判据；
* 谁哪天把 job service 里的 `report.to_public_dict()` 改成 `to_internal_dict()`，没有东西会红。

**为什么要再手写一份清单**：如果判据只有"声明了哪些就藏哪些"，那 `_INTERNAL_KEYS` 里删掉
`stage_errors` 之后两边一起变小，判据照样绿——它检查的是自洽，不是"该藏的藏了"。
所以这里有两层：`MUST_BE_HIDDEN` 是**人的断言**（哪几个字段绝不能出门），`_INTERNAL_KEYS` 是代码的
实现；判据让两者对齐，任何一边动了另一边没跟就红。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.services.portfolio_report_schema as portfolio_schema
import app.services.project_report_schema as project_schema
import app.services.resume_report_schema as resume_schema

SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"

# 人的断言：这几类字段是排查用的内证据，候选人一个都不该看到。
MUST_BE_HIDDEN = {
    "resume": {
        "model_reported_total",
        "provenance",
        "stage_errors",
        "redline_rejected",
        "interview_rejected",
        "note_anchor_stats",
    },
    "project": {
        "provenance",
        "stage_errors",
        "red_line_rejected",
        "diagram_rejected",
        "advice_rejected",
        "questions_rejected",
        "metric_gap_evidence",
        "stack_footprint",
        "peer_totals",
    },
    "portfolio": {
        "provenance",
        "stage_errors",
        "red_line_rejected",
        "compare_rejected",
        "capability_rejected",
        "diagram_rejected",
        "advice_rejected",
        "questions_rejected",
        "per_project_metric_gaps",
        "stack_reuse",
        "duplicate_evidence",
        "peer_scores",
        "shared_stack_dropped",
    },
}

CASES = [
    pytest.param("resume", resume_schema, lambda: resume_schema.Report(resume_id=1), id="resume"),
    pytest.param(
        "project",
        project_schema,
        lambda: project_schema.ProjectReport(resume_id=1, project_index=0),
        id="project",
    ),
    pytest.param(
        "portfolio",
        portfolio_schema,
        lambda: portfolio_schema.PortfolioReport(resume_id=1),
        id="portfolio",
    ),
]


@pytest.mark.parametrize(("name", "module", "make"), CASES)
def test_nothing_from_the_policy_list_reaches_the_public_view(name, module, make):
    report = make()
    public = report.to_public_dict()

    leaked = MUST_BE_HIDDEN[name] & set(public)
    assert not leaked, f"{name}: 公开视图里出现了 {sorted(leaked)}"


@pytest.mark.parametrize(("name", "module", "make"), CASES)
def test_the_code_list_is_not_narrower_than_the_policy(name, module, make):
    """代码那份清单不许比人的断言窄：删掉一个就红（这正是"自洽判据"漏掉的那个方向）。"""
    declared = set(module._INTERNAL_KEYS)
    missing = MUST_BE_HIDDEN[name] - declared
    assert not missing, f"{name}: _INTERNAL_KEYS 少了 {sorted(missing)}，这些字段现在会出门"


@pytest.mark.parametrize(("name", "module", "make"), CASES)
def test_declared_keys_are_real_and_exactly_hidden(name, module, make):
    """维护向的两条：清单里没有过期名字；隐藏的集合与清单逐项相等。"""
    declared = set(module._INTERNAL_KEYS)
    report = make()
    internal = report.to_internal_dict()
    public = report.to_public_dict()

    stale = declared - set(internal)
    assert not stale, f"{name}: _INTERNAL_KEYS 里有视图根本没产出的名字 {sorted(stale)}"

    hidden = set(internal) - set(public)
    assert hidden == declared, (
        f"{name}: 实际隐藏 {sorted(hidden)} 与声明 {sorted(declared)} 不一致；"
        f"多藏 {sorted(hidden - declared)}、漏藏 {sorted(declared - hidden)}"
    )


def test_job_services_serialize_the_public_view_not_the_internal_one():
    """落库那一份必须来自 `to_public_dict()`；改成 `to_internal_dict()` 就是把内证据发给浏览器。"""
    for filename in (
        "report_job_service.py",
        "project_report_job_service.py",
        "portfolio_report_job_service.py",
    ):
        source = (SERVICES / filename).read_text(encoding="utf-8")
        assert "to_internal_dict" not in source, f"{filename} 里出现了 to_internal_dict"
        assert "report.to_public_dict()" in source, f"{filename} 没有用公开视图落库"
