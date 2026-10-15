"""组合分析的复核：模型只能提出，服务端来判。

这一族最值得钉的四条界：
* **逐字证据**：红线提名里那段引文不在被选项目原文的并集里就整条作废；
* **失败粒度跟着缺陷粒度走**：横向对比一个数字只撤那一格、叙事主线一条要点只撤那一条，
  不是一处不合格就让整节缺席（D236 那轮在真简历上学的）；
* **能算的不问模型**：覆盖结论、共用栈、位次那一维、排列那一格都由服务端出；
* **2~N 泛化**：阶段数、表格列数、选中集校验都跟着项目数走。
"""

from __future__ import annotations

from app.services import portfolio_report_rubric as rubric
from app.services import portfolio_report_service as svc
from app.services.portfolio_report_schema import (
    PortfolioReport,
    build_portfolio_excerpts,
    raw_entries_text,
    universe_text,
)
from tests.portfolio_report_payloads import FIRST, SECOND, THIRD
from tests.portfolio_report_payloads import advice_payload as _shared_advice
from tests.portfolio_report_payloads import diagram_payload as _shared_diagram
from tests.portfolio_report_payloads import profile_payload as _shared_profile
from tests.portfolio_report_payloads import questions_payload as _shared_questions

INDICES = [0, 1, 2]
ENTRIES = [FIRST, SECOND, THIRD]
QUOTES = raw_entries_text(ENTRIES, INDICES)
CELL_BAD = svc.CELL_DROPPED_NOTE


def _report(indices: list[int] | None = None) -> PortfolioReport:
    picked = indices or INDICES
    report = PortfolioReport(
        resume_id=1,
        project_indices=picked,
        projects=build_portfolio_excerpts(ENTRIES, picked),
        peer_scores=[{"project_index": index, "total": None} for index in picked],
    )
    tech = {int(row["project_index"]): [str(t) for t in row["tech"]] for row in report.projects}
    report.stack_reuse = rubric.stack_reuse(tech)
    return report


def _dimensions_payload() -> dict:
    return {
        "d1_role_signal": {"score": 20, "note": "「项目描述：合同原文与扫描件存 MinIO」这一条把方向对上了"},
        "d2_combo_distinct": {"score": 16, "note": "「检索命中率没有前后对比」这一条是三个项目共有的洞"},
        "d3_metric": {"score": 14, "note": "职责第 2 条那个 9.3% 没写怎么测"},
        "d4_growth_line": {"score": 11, "note": "从解析到编排到图谱，线是有的"},
        "d5_interview": {"score": 10, "note": "「只留一个留哪个」这一问在原文里给不出投入分配"},
    }


def _profile_payload(**overrides) -> dict:
    return _shared_profile(INDICES, **overrides)


def _diagram_payload(indices: list[int] | None = None) -> dict:
    return _shared_diagram(indices or INDICES)


def _advice_payload() -> dict:
    return _shared_advice(INDICES)


def _questions_payload(count: int = 12) -> dict:
    return _shared_questions(INDICES, count)


def _validate_profile(payload: dict):
    return svc.validate_profile(payload, INDICES, QUOTES, _report().stack_reuse)


# ------------------------------------------------------------------ 选中集
def test_选中集至少两个且去重排序():
    assert svc.selected_indices(ENTRIES, [2, 0, 1, 0]) == [0, 1, 2]
    try:
        svc.selected_indices(ENTRIES, [1])
    except ValueError as exc:
        assert "至少" in str(exc)
    else:
        raise AssertionError("只给一个项目不该被当成组合")


def test_选中集越界要报错():
    try:
        svc.selected_indices(ENTRIES, [0, 9])
    except ValueError as exc:
        assert "第 10 个项目" in str(exc)
    else:
        raise AssertionError("不存在的序号不该被接受")


def test_表头均分一格在有与没有时写法不同():
    report = _report()
    report.peer_scores = [
        {"project_index": 0, "total": 88},
        {"project_index": 1, "total": 79},
        {"project_index": 2, "total": None},
    ]
    assert report.average_cell().startswith("83.5")
    assert "2/3" in report.average_cell()
    report.peer_scores = [{"project_index": 0, "total": None}] * 3
    assert report.average_cell() == "还没跑过单项目分析，这一格空着"


# ------------------------------------------------------------------ 一、组合档案
def test_正常载荷读成六维与七行对比():
    profile, rejected = _validate_profile(_profile_payload())
    assert rejected == []
    assert len(profile["dimensions"]) == 6
    # 20+16+14+11+10 = 71 是模型给的五维，位次那一维由服务端算出 4 分（占第 1~3 位）。
    assert rubric.total_of(profile["dimensions"]) == 75
    assert len(profile["compare"]) == 7
    assert all(len(row["cells"]) == 3 for row in profile["compare"])
    assert [row["key"] for row in profile["capabilities"]] == [
        "hybrid_retrieval",
        "knowledge_graph",
        "agent_orchestration",
        "refusal",
        "llmops",
    ]
    assert profile["capabilities"][0]["verdict"]["word"] == "强"


def test_红线证据不逐字就整条作废():
    payload = _profile_payload(red_lines=[{"key": "others_work_combo", "quote": "我主导了全部三个项目", "why": "归属"}])
    profile, rejected = _validate_profile(payload)
    assert profile["excluded_by"] == []
    assert {"reason": "quote_not_verbatim", "detail": "others_work_combo"} in rejected


def test_红线逐字命中就判出局():
    payload = _profile_payload(
        red_lines=[{"key": "others_work_combo", "quote": "负责召回与重排两段", "why": "三个都写成自己主导"}]
    )
    profile, rejected = _validate_profile(payload)
    assert len(profile["excluded_by"]) == 1
    assert profile["excluded_by"][0]["label"] == "整组不是本人参与却都写成自己的"
    assert rejected == []


def test_代码判的那一条不接受模型提名():
    payload = _profile_payload(red_lines=[{"key": "duplicate_projects", "quote": "负责召回与重排两段", "why": "x"}])
    _, rejected = _validate_profile(payload)
    assert {"reason": "not_model_judged", "detail": "duplicate_projects"} in rejected


def test_难度不在白名单里只记差异():
    payload = _profile_payload(difficulty={"level": "L5+", "reason": "参考件那么写"})
    profile, rejected = _validate_profile(payload)
    assert profile["difficulty"]["level"] == ""
    assert {"reason": "bad_difficulty_level", "detail": "L5+"} in rejected


def test_横向对比少一列用一句话补上不丢整行():
    rows = []
    for key in rubric.COMPARE_ROW_KEYS:
        cells = [{"project_index": index, "text": "说法"} for index in (0, 1)]
        rows.append({"row": key, "cells": cells})
    profile, rejected = _validate_profile(_profile_payload(compare=rows))
    assert len(profile["compare"]) == 7
    assert all("2" in row["cells"] and "没有写到" in row["cells"]["2"] for row in profile["compare"])
    assert any(row["reason"] == "compare_cells_incomplete" for row in rejected)


def test_横向对比一个数字只撤那一格():
    rows = []
    for key in rubric.COMPARE_ROW_KEYS:
        rows.append(
            {
                "row": key,
                "cells": [
                    {"project_index": index, "text": "这一格说的是 92% 的提升" if index == 1 else "这一格没有新数字"}
                    for index in INDICES
                ],
            }
        )
    profile, rejected = _validate_profile(_profile_payload(compare=rows))
    assert len(profile["compare"]) == 7
    bad = [row for row in profile["compare"] if row["key"] == "domain"][0]
    assert bad["cells"]["1"] == CELL_BAD
    assert bad["cells"]["0"] == "这一格没有新数字"
    assert sum(row["reason"] == "compare_cell_invented_number" for row in rejected) == 7


def test_整行都被撤下的那一行不进表():
    rows = [
        {
            "row": key,
            "cells": [{"project_index": index, "text": "凭空 92% 的提升"} for index in INDICES],
        }
        for key in rubric.COMPARE_ROW_KEYS
    ]
    profile, rejected = _validate_profile(_profile_payload(compare=rows))
    assert profile["compare"] == []
    assert sum(row["reason"] == "compare_row_all_dropped" for row in rejected) == 7


def test_对比表认得原文里的真实数字():
    rows = [
        {
            "row": key,
            "cells": [
                {"project_index": index, "text": "初稿由人工约 30 - 60 分钟缩短至 5 - 10 分钟"} for index in INDICES
            ],
        }
        for key in rubric.COMPARE_ROW_KEYS
    ]
    profile, rejected = _validate_profile(_profile_payload(compare=rows))
    assert profile["compare"][0]["cells"]["0"] == "初稿由人工约 30 - 60 分钟缩短至 5 - 10 分钟"
    assert not any(row["reason"] == "compare_cell_invented_number" for row in rejected)


def test_白名单外的对比行与乱序号都不取():
    payload = _profile_payload(
        compare=[
            {"row": "zodiac", "cells": [{"project_index": 0, "text": "x"}]},
            {"row": "domain", "cells": [{"project_index": 7, "text": "越界的项目序号"}]},
        ]
    )
    _, rejected = _validate_profile(payload)
    assert {"reason": "compare_row_off_list", "detail": "zodiac"} in rejected
    assert any(row["reason"] == "compare_index_out_of_list" for row in rejected)


def test_共用栈只保留真在交集里的那几只():
    profile, rejected = _validate_profile(_profile_payload(shared_stack=["FastAPI", "Kafka"]))
    assert profile["shared_stack_kept"] == ["FastAPI"]
    assert profile["shared_stack_dropped"] == ["Kafka"]
    assert {"reason": "shared_stack_dropped", "detail": "Kafka"} in rejected


def test_补齐动作里冒出新数字的那条风险被丢掉():
    payload = _profile_payload(
        risks=[
            {"point": "归因未拆", "detail": "只写了 45% 的提升", "fix": "跑对照"},
            {"point": "业务效果薄", "detail": "没有采纳率", "fix": "补埋点"},
            {"point": "骨架相同", "detail": "说不清差异", "fix": "各补一条决策"},
        ]
    )
    profile, rejected = _validate_profile(payload)
    assert [row["point"] for row in profile["risks"]] == ["业务效果薄", "骨架相同"]
    assert any(row["reason"] == "risk_invented_number" for row in rejected)


def test_机制字眼出现在风险栏里整条不要():
    payload = _profile_payload(
        risks=[
            {"point": "命中出局阈值", "detail": "门禁", "fix": "改口径"},
            {"point": "归因未拆", "detail": "几项一起上", "fix": "跑对照"},
            {"point": "业务效果薄", "detail": "没有采纳率", "fix": "补埋点"},
            {"point": "骨架相同", "detail": "说不清差异", "fix": "各补一条决策"},
        ]
    )
    profile, rejected = _validate_profile(payload)
    assert "命中出局阈值" not in [row["point"] for row in profile["risks"]]
    assert any(row["reason"] == "forbidden_word" for row in rejected)


def test_五维理由一处都不点名位置时记下来():
    payload = _profile_payload(
        dimensions={
            key: {"score": 10, "note": "整体还可以"}
            for key in ("d1_role_signal", "d2_combo_distinct", "d3_metric", "d4_growth_line", "d5_interview")
        }
    )
    _, rejected = _validate_profile(payload)
    assert any(row["reason"] == "all_notes_unanchored" for row in rejected)


def test_两个项目的组合也能跑完整复核():
    report = _report([0, 1])
    payload = {
        "summary": {"projects_line": "两个项目", "common_skeleton": "召回", "difference_line": "确定性"},
        "dimensions": _dimensions_payload(),
        "red_lines": [],
        "difficulty": {"level": "L3", "reason": "两类范式"},
        "compare": [
            {"row": key, "cells": [{"project_index": i, "text": "说法"} for i in (0, 1)]}
            for key in rubric.COMPARE_ROW_KEYS
        ],
        "capabilities": [
            {"capability": "hybrid_retrieval", "cells": [{"project_index": i, "cell": "重点覆盖"} for i in (0, 1)]}
        ],
        "shared_stack": [],
        "risks": [{"point": "a", "detail": "b", "fix": "c"}] * 3,
    }
    profile, rejected = svc.validate_profile(payload, [0, 1], raw_entries_text(ENTRIES, [0, 1]), report.stack_reuse)
    assert rejected == []
    assert profile["capabilities"][0]["verdict"]["word"] == "极强"
    assert all(len(row["cells"]) == 2 for row in profile["compare"])


# ------------------------------------------------------------------ 二、组合图解
def _validate_diagrams(payload: dict, report: PortfolioReport | None = None):
    return svc.validate_diagrams(payload, report or _report())


def test_图解正常形状带五轮与每段一条():
    diagrams, rejected = _validate_diagrams(_diagram_payload())
    assert rejected == []
    assert len(diagrams["narrative"]["stages"]) == 3
    assert len(diagrams["rounds"]) == 5
    assert diagrams["rounds"][2]["decisive"] is True
    assert diagrams["stack"]["shared"] == _report().stack_reuse["shared"]


def test_阶段数不等于项目数时叙事主线整块缺席():
    payload = _diagram_payload()
    payload["narrative"]["stages"] = payload["narrative"]["stages"][:2]
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams["narrative"] is None
    assert diagrams["rounds"] is not None
    assert any(row["reason"] == "narrative_stages_missing" for row in rejected)


def test_同一个项目被讲两次那段不算():
    payload = _diagram_payload()
    payload["narrative"]["stages"][1]["project_index"] = 0
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams["narrative"] is None
    assert any(row["reason"] == "stage_index_duplicate" for row in rejected)


def test_一条要点带新数字只撤那一条不撤整段():
    payload = _diagram_payload()
    payload["narrative"]["stages"][0]["points"] = [
        "这条写了 45% 的提升",
        "把依据与判断分开",
        "不足时不硬下结论",
        "留下自己的口径",
    ]
    diagrams, rejected = _validate_diagrams(payload)
    stage = diagrams["narrative"]["stages"][0]
    assert len(stage["points"]) == 3
    assert any(row["reason"] == "point_invented_number" for row in rejected)


def test_要点少于三条的那一段不算进主线():
    payload = _diagram_payload()
    payload["narrative"]["stages"][1]["points"] = ["只有一条"]
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams["narrative"] is None
    assert {"reason": "stage_points_thin", "detail": "1:1"} in rejected


def test_轮次少一轮时序图就不画():
    payload = _diagram_payload()
    payload["rounds"] = payload["rounds"][:4]
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams["rounds"] is None
    assert any(row["reason"] == "rounds_incomplete" for row in rejected)


def test_轮次键白名单外的整条不要():
    payload = _diagram_payload()
    payload["rounds"][0]["key"] = "warmup"
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams["rounds"] is None
    assert {"reason": "round_off_list", "detail": "warmup"} in rejected


def test_解读段落里冒出新数字那一格留空不撤整节():
    payload = _diagram_payload()
    payload["reuse_read"] = "共用栈说明稳定，一共节省了 40% 的人力"
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams["reuse_read"] == ""
    assert diagrams["unique_read"] == payload["unique_read"]
    assert any(row["reason"] == "field_invented_number" and row["detail"] == "reuse_read" for row in rejected)


def test_主线与时序都不合格时整节缺席():
    payload = _diagram_payload()
    payload["narrative"]["stages"] = []
    payload["rounds"] = []
    diagrams, rejected = _validate_diagrams(payload)
    assert diagrams is None
    assert {"reason": "diagrams_both_absent"} in rejected


# ------------------------------------------------------------------ 三、使用建议
def test_使用建议正常形状里排列那一格由服务端渲染():
    advice, rejected = svc.validate_advice(_advice_payload(), _report())
    assert rejected == []
    assert advice["arrangements"][0]["rendered"] == "PJ-01 → PJ-02 → PJ-03"
    assert advice["arrangements"][1]["rendered"] == "PJ-03 → PJ-02 → PJ-01"
    assert advice["default_index"] == 0
    assert len(advice["asked_before"]) == 3


def test_不是全排列的排法整行丢掉():
    payload = _advice_payload()
    payload["arrangements"][0]["project_indices"] = [0, 1, 9]
    advice, rejected = svc.validate_advice(payload, _report())
    assert [row["order"] for row in advice["arrangements"]] == [[2, 1, 0], [2, 0, 1]]
    assert any(row["reason"] == "arrangement_not_a_permutation" for row in rejected)


def test_少一种排法就不成建议节():
    payload = _advice_payload()
    payload["arrangements"] = payload["arrangements"][:1]
    advice, rejected = svc.validate_advice(payload, _report())
    assert advice is None
    assert {"reason": "arrangements_thin"} in rejected


def test_默认排法指向不存在的行时收回头一条():
    payload = _advice_payload()
    payload["default_choice"] = 9
    advice, rejected = svc.validate_advice(payload, _report())
    assert advice["default_index"] == 0
    assert {"reason": "default_choice_out_of_range", "detail": 9} in rejected


def test_补齐后预计不点维度就整行不要():
    payload = _advice_payload()
    payload["strengthen"][1]["expected"] = "整体更完整"
    advice, rejected = svc.validate_advice(payload, _report())
    assert [row["gap"] for row in advice["strengthen"]] == ["归因都合在一起测", "叙事顺序没有设计"]
    assert {"reason": "expected_no_dimension", "detail": "整体更完整"} in rejected


def test_引用红线少一档整节不成立():
    payload = _advice_payload()
    del payload["citation"]["breaks"]
    advice, rejected = svc.validate_advice(payload, _report())
    assert advice is None
    assert {"reason": "advice_table_incomplete"} in rejected


def test_可借鉴里出现省略写法那一档被撤下():
    payload = _advice_payload()
    payload["citation"]["adapt"] = "需改造的部分同上"
    advice, rejected = svc.validate_advice(payload, _report())
    assert advice is None
    assert {"reason": "citation_field_rejected", "detail": "adapt"} in rejected


# ------------------------------------------------------------------ 四、跨项目面试
def _question(index: int, status: str = "可答", kind: str = "差异与取舍") -> dict:
    return {
        "question": f"第 {index + 1} 问：这三个项目有什么本质不同",
        "kind": kind,
        "answer": "骨架确实相同，解决的核心问题不一样。" + "一个解决依据从哪来，一个解决判断能不能复现，"
        "一个解决系统能不能越用越好，所以是同一套能力在几种约束下的不同组合。" * 2,
        "followups": [{"kind": "为什么", "text": "追问一"}, {"kind": "数据", "text": "追问二"}],
        "status": status,
        "missing": ["缺一个分项差值"] if status != "可答" else [],
        "risk_ref": None,
    }


def test_题目正常形状数出来是十二题():
    items, dist, rejected = svc.validate_questions(_questions_payload(), universe_text(_report().projects), 3)
    assert rejected == []
    assert dist == {
        "total": 12,
        "target": 12,
        "by_kind": {kind: 2 for kind in rubric.QUESTION_KINDS},
        "answerable": 11,
        "weak": 1,
        "high_risk": 0,
    }
    assert [item["no"] for item in items] == list(range(1, 13))


def test_题型不在组合六个里的那题不要():
    payload = _questions_payload()
    payload["questions"][0]["kind"] = "背景与定位"
    _, dist, rejected = svc.validate_questions(payload, QUOTES, 3)
    assert dist["total"] == 11
    assert any(row["reason"] == "bad_kind" for row in rejected)


def test_答案太短与新数字都拦在同一题上():
    universe = universe_text(_report().projects)
    payload = _questions_payload()
    payload["questions"][0]["answer"] = "太短了"
    payload["questions"][1]["answer"] = (
        "我们节省了 40% 的人力成本，" + "口径写在规则表里，异常归因那一层交给规则判定，" * 6
    )
    items, dist, rejected = svc.validate_questions(payload, universe, 3)
    assert dist["total"] == 10
    reasons = [row["reason"] for row in rejected]
    assert "answer_too_short" in reasons and "invented_number" in reasons


def test_高危指不回第几条风险就降成需补强():
    payload = _questions_payload()
    payload["questions"][3]["status"] = "高危"
    payload["questions"][3]["risk_ref"] = 9
    payload["questions"][3]["missing"] = ["说不清投入分配"]
    items, dist, rejected = svc.validate_questions(payload, QUOTES, 3)
    assert dist["high_risk"] == 0
    assert dist["weak"] == 2
    assert any(row["reason"] == "risk_ref_out_of_range" and row["detail"] == 9 for row in rejected)


def test_高危指得回就留着并记序号():
    payload = _questions_payload()
    payload["questions"][3]["status"] = "高危"
    payload["questions"][3]["risk_ref"] = 2
    payload["questions"][3]["missing"] = ["说不清时间线"]
    items, dist, _ = svc.validate_questions(payload, QUOTES, 3)
    assert dist["high_risk"] == 1
    assert items[3]["risk_ref"] == 2


def test_追问必须两轮且标签在白名单里():
    universe = QUOTES
    payload = _questions_payload()
    payload["questions"][0]["followups"] = payload["questions"][0]["followups"][:1]
    payload["questions"][1]["followups"][1]["kind"] = "工资"
    _, dist, rejected = svc.validate_questions(payload, universe, 3)
    assert dist["total"] == 10
    reasons = [row["reason"] for row in rejected]
    assert "followup_count" in reasons and "bad_followup_kind" in reasons


def test_需补强不点名缺什么就不算一题():
    payload = _questions_payload()
    payload["questions"][10]["missing"] = []
    _, dist, rejected = svc.validate_questions(payload, QUOTES, 3)
    assert dist["total"] == 11
    assert "missing_not_named" in [row["reason"] for row in rejected]


def test_题数分布里各题型都数得到():
    items, dist, _ = svc.validate_questions(_questions_payload(), QUOTES, 3)
    assert sum(dist["by_kind"].values()) == 12
    assert svc.practice_backfill(items)["must_practice"] == "Q11"


def test_待补标记能从档案摊到第三节():
    report = _report()
    report.compare = {
        "rows": [
            {
                "key": "metric",
                "label": "关键指标",
                "cells": {"0": "【待补：按上线前后各跑一遍得到差值】", "1": "没有", "2": "没有"},
            }
        ]
    }
    assert svc.collect_todos(report) == ["【待补：按上线前后各跑一遍得到差值】"]
