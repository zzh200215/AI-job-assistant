"""单项目分析的服务端复核：模型只能提出，不能自证。

每一条都按"一个变异只红它自己那条"写：给一份合法载荷，再单独把某一处改坏。
"""

from project_report_payloads import (
    BODY,
    ENTRY,
    PEERS,
    PROJ,
    advice_payload,
    diagrams_payload,
    profile_payload,
    question,
    question_diagram,
    questions_payload,
)

from app.services import project_report_service as svc
from app.services.project_report_schema import build_project_excerpt, raw_entry_text


def _profile(**override):
    payload = profile_payload()
    payload.update(override)
    return payload


def _run_profile(payload, entry_text=BODY, peers=PEERS):
    return svc.validate_profile(payload, 0, entry_text, peers)


# ------------------------------------------------------------------ 1.2 逐字摘录
def test_excerpt_splits_the_resume_own_section_titles():
    excerpt = build_project_excerpt(ENTRY, 0)
    labels = [row["label"] for row in excerpt["sections"]]
    assert "项目描述（简历原文）" in labels
    assert "个人职责（简历原文）" in labels
    assert "项目成果（简历原文）" in labels
    assert excerpt["rank"] == 1 and excerpt["code"] == "PJ-01"
    original = raw_entry_text(ENTRY)
    for row in excerpt["sections"]:
        for line in row["lines"]:
            assert line in original


def test_excerpt_does_not_invent_sections_when_the_resume_has_no_titles():
    entry = {"name": "无标题项目", "desc": "只做了一件事，另一件事也做了。\n还有一句。"}
    excerpt = build_project_excerpt(entry, 2)
    assert [row["label"] for row in excerpt["sections"]] == ["项目原文（这份简历里没有分栏标题）"]
    assert excerpt["rank"] == 3 and excerpt["code"] == "PJ-03"


def test_a_sentence_starting_like_a_title_is_not_treated_as_a_title():
    entry = {"name": "误判测试", "desc": "成果展示平台负责把报表导出成邮件。\n另一句。"}
    excerpt = build_project_excerpt(entry, 0)
    assert [row["label"] for row in excerpt["sections"]] == ["项目原文（这份简历里没有分栏标题）"]


# ------------------------------------------------------------------ 一、项目档案
def test_profile_reads_dimensions_and_computes_nothing_from_the_model():
    profile, rejected = _run_profile(profile_payload())
    assert rejected == []
    rows = profile["dimensions"]
    assert [row["key"] for row in rows] == [
        "d1_role_signal",
        "d2_depth",
        "d3_metric",
        "d4_transfer",
        "d5_interview",
        "d6_rank",
    ]
    assert rows[-1]["score"] == 5  # 第 1 位，服务端给的
    assert profile["anchor_stats"] == {"scored": 5, "unanchored_keys": []}
    # 其它项目也一样把位次那一维算进合计（20+18+12+10+9 再加第 2 位的 3 分），
    # 否则"占这份简历多少"的两边不是同一个量。
    assert profile["peer_totals"] == [{"project_index": 1, "total": 72}]


def test_red_line_quote_must_be_verbatim_in_the_project_text():
    bogus = {"key": "others_work", "quote": "这个项目是我一个人从零主导完成的", "why": "一问分工就露"}
    profile, rejected = _run_profile(_profile(red_lines=[bogus]))
    assert profile["excluded_by"] == []
    assert [row["reason"] for row in rejected] == ["quote_not_verbatim"]

    real = {"key": "others_work", "quote": "针对证据冲突与上下文过长触发 reset 重组证据包", "why": "整段写成自己主导"}
    profile, rejected = _run_profile(_profile(red_lines=[real]))
    assert [row["key"] for row in profile["excluded_by"]] == ["others_work"]
    assert rejected == []


def test_red_line_matching_ignores_line_breaks_and_indentation():
    real = {"key": "template_smell", "quote": "使用 Qwen 7B 做 LoRA 适配\n验证", "why": "跨行也要认"}
    profile, rejected = _run_profile(_profile(red_lines=[real]))
    assert [row["key"] for row in profile["excluded_by"]] == ["template_smell"]
    assert rejected == []


def test_code_judged_red_lines_are_not_taken_from_the_model():
    payload = _profile(
        red_lines=[{"key": "no_baseline", "quote": "输出统一落到 6 段式审查底稿。", "why": "自报无基线"}]
    )
    profile, rejected = _run_profile(payload)
    assert profile["excluded_by"] == []
    assert [row["reason"] for row in rejected] == ["not_model_judged"]


def test_duplicate_red_line_key_is_refused():
    line = {"key": "template_smell", "quote": "使用 Qwen 7B 做 LoRA 适配验证", "why": "模板味"}
    profile, rejected = _run_profile(_profile(red_lines=[line, dict(line)]))
    assert len(profile["excluded_by"]) == 1
    assert [row["reason"] for row in rejected] == ["duplicate_red_line"]


def test_highlight_with_a_number_that_is_not_in_the_resume_is_refused():
    payload = _profile(highlights=[{"metric": "命中率", "value": "92%", "basis": "样例集"}])
    profile, rejected = _run_profile(payload)
    assert profile["highlights"] == []
    assert [row["reason"] for row in rejected] == ["invented_number"]


def test_highlight_may_leave_a_pending_value_instead_of_inventing_one():
    payload = _profile(
        highlights=[{"metric": "并发上限", "value": "【待补：单卡压测得到的并发上限】", "basis": "验证环境"}]
    )
    profile, rejected = _run_profile(payload)
    assert len(profile["highlights"]) == 1
    assert rejected == []


def test_peer_dimensions_only_accept_projects_that_exist():
    payload = _profile(
        peer_dimensions=[
            {"project_index": 0, "dimensions": {"d1_role_signal": 20}},
            {"project_index": 9, "dimensions": {"d1_role_signal": 20}},
        ]
    )
    profile, rejected = _run_profile(payload)
    assert profile["peer_totals"] == []
    assert [row["reason"] for row in rejected] == ["peer_out_of_list", "peer_out_of_list"]


def test_all_five_notes_being_generic_is_recorded_not_fixed():
    generic = {"score": 10, "note": "建议补充量化指标与岗位关键词。"}
    payload = _profile(
        dimensions={
            key: dict(generic) for key in ("d1_role_signal", "d2_depth", "d3_metric", "d4_transfer", "d5_interview")
        }
    )
    profile, rejected = _run_profile(payload)
    assert profile["anchor_stats"]["unanchored_keys"] == [
        "d1_role_signal",
        "d2_depth",
        "d3_metric",
        "d4_transfer",
        "d5_interview",
    ]
    assert [row["reason"] for row in rejected] == ["all_notes_unanchored"]


def test_contribution_is_computed_from_scores_never_reported():
    got = svc.compute_contribution(0, 80, [{"project_index": 1, "total": 69}])
    # 第 2 位的系数是 3：本项目 80×5，peer 69×3。
    assert got["coefficient"] == 5
    assert got["share"] == round(400 / (400 + 207) * 100, 1)
    assert got["persuasion"] == round((400 + 207) / 10, 1)
    unknown = svc.compute_contribution(0, 80, [{"project_index": 1, "total": None}])
    assert unknown["share"] is None and unknown["persuasion"] is None


def test_code_evidence_is_collected_but_never_decides_the_score():
    gaps = svc.rubric.metric_gap_clauses("建立标准化审查流程，大幅提升审查效率；误报率下降 90%。")
    assert [row["kind"] for row in gaps] == ["no_number", "single_number"]
    # 落点只看正文：把技术栈那串本身也算进被检串，每一项都会"自己落点"，这条判据就废了。
    foot = svc.rubric.stack_footprint(ENTRY["tech"], PROJ)
    assert "Redis" in foot["missing"] and "Neo4j" not in foot["missing"]


# ------------------------------------------------------------------ 二、项目图解
def test_all_four_diagrams_pass_with_anchored_sources():
    diagrams, rejected = svc.validate_diagrams(diagrams_payload(), BODY)
    assert diagrams is not None
    assert diagrams["figures"] == list(svc.DIAGRAM_KEYS)
    assert rejected == []
    # 节点编号由服务端按顺序重排，模型给的 7/8/9/10 不取。
    assert [row["no"] for row in diagrams["core_flow"]["nodes"]] == [1, 2, 3, 4]


def test_function_arch_without_the_boundary_sentence_is_dropped():
    payload = diagrams_payload()
    payload["function_arch"]["boundary"] = "这一层用了几个组件。"
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert diagrams is not None and "function_arch" not in diagrams["figures"]
    assert [row["reason"] for row in rejected if row.get("diagram") == "function_arch"] == [
        "layers_boundary_or_deep_dive_incomplete"
    ]
    assert diagrams["figures"] == ["core_flow", "system_arch", "sequence"]


def test_source_column_must_point_at_the_resume():
    payload = diagrams_payload()
    payload["core_flow"]["deep_dive"] = [{"where": "为什么这么切", "point": "好定位", "source": "见上文"}]
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert "core_flow" not in diagrams["figures"]
    reasons = [row["reason"] for row in rejected if row.get("diagram") == "core_flow"]
    assert "source_not_anchored" in reasons


def test_message_to_an_unknown_lane_is_dropped_and_recorded():
    payload = diagrams_payload()
    payload["sequence"]["messages"][2]["to"] = "并不存在的泳道"
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert [row["reason"] for row in rejected if row.get("diagram") == "sequence"] == ["lane_unknown"]
    assert len(diagrams["sequence"]["messages"]) == 4

    payload = diagrams_payload()
    payload["sequence"]["messages"][2]["to"] = "并不存在的泳道"
    payload["sequence"]["messages"][3]["from"] = "并不存在的泳道"
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert "sequence" not in diagrams["figures"]
    assert [row["reason"] for row in rejected if row.get("diagram") == "sequence"] == [
        "lane_unknown",
        "lane_unknown",
        "lanes_messages_branches_incomplete",
    ]


def test_a_diagram_inventing_a_number_drops_only_that_diagram():
    payload = diagrams_payload()
    payload["system_arch"]["layers"][0]["components"][0]["line"] = "缓存命中率 92% 之后走这条路"
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert "system_arch" not in diagrams["figures"]
    assert diagrams["figures"] == ["function_arch", "core_flow", "sequence"]
    assert [row["reason"] for row in rejected if row.get("diagram") == "system_arch"] == ["invented_number_diagram"]


def test_ordinal_addresses_are_not_read_as_invented_numbers():
    payload = diagrams_payload()
    payload["core_flow"]["deep_dive"].append(
        {"where": "第 3 条那一步", "point": "为什么单独成节点", "source": "职责第 5 条"}
    )
    _, rejected = svc.validate_diagrams(payload, BODY)
    assert [row for row in rejected if row.get("reason") == "invented_number_diagram"] == []


def test_mechanism_words_kill_the_whole_figure_section():
    payload = diagrams_payload()
    payload["reading_note"] = "这一层是门禁，过不去就不出图。"
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert diagrams is None
    assert [row["reason"] for row in rejected][-1] == "forbidden_word_diagram"


def test_background_and_needs_are_all_or_nothing():
    payload = diagrams_payload()
    payload["needs"]["items"] = payload["needs"]["items"][:1]
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert diagrams is None
    assert [row["reason"] for row in rejected] == ["background_or_needs_incomplete"]


def test_prose_outside_the_four_figures_is_scanned_too():
    payload = diagrams_payload()
    payload["background"] = "这套系统把准确率提到 99%。"
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert diagrams is None
    assert [row["reason"] for row in rejected] == ["invented_number_prose"]


def test_node_count_above_ten_is_refused():
    payload = diagrams_payload()
    payload["core_flow"]["nodes"] = [{"title": f"节点{i}", "lines": ["做一件事"]} for i in range(11)]
    diagrams, rejected = svc.validate_diagrams(payload, BODY)
    assert "core_flow" not in diagrams["figures"]
    assert [row["reason"] for row in rejected if row.get("diagram") == "core_flow"] == ["nodes_or_fallbacks_incomplete"]


# ------------------------------------------------------------------ 三、使用建议
class _StubReport:
    difficulty = {"level": "L5", "reason": "三类范式叠加"}
    excerpt = build_project_excerpt(ENTRY, 0)
    dimensions: list = []
    highlights: list = []
    risks: list = []


def test_strengthen_rows_must_name_a_dimension():
    payload = advice_payload()
    payload["strengthen"][1]["expected"] = "整体就更经得起追问了"
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert len(advice["strengthen"]) == 1
    assert [row["reason"] for row in rejected] == ["expected_no_dimension"]


def test_difficulty_cell_always_comes_from_the_profile():
    payload = advice_payload()
    payload["teaching"]["level"] = "L2"
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert advice["level"] == "L5" and advice["level_source"] == "profile"
    assert [row["reason"] for row in rejected] == ["difficulty_overridden_by_profile"]


def test_practice_backfill_keys_are_not_taken_from_this_call():
    payload = advice_payload()
    payload["practice"]["must_practice"] = "Q1、Q2"
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert "must_practice" not in advice["practice"]
    assert [row["reason"] for row in rejected] == ["practice_keys_belong_to_section_four"]


def test_one_bad_number_drops_that_row_not_the_whole_section():
    """2026-10-14 真简历走过一遍才改的：旧写法是一条数字让四张没毛病的表陪葬。"""
    payload = advice_payload()
    payload["reuse"]["counterexample"] = "照搬「命中率 92%」会被追问前置环节的边界"
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert advice is not None
    assert "counterexample" not in advice["reuse"]
    assert set(advice["teaching"]) == {"suitable", "steps", "entry", "stage"}
    assert [row["reason"] for row in rejected] == ["invented_number"]
    assert rejected[0]["table"] == "3.2"


def test_a_strengthen_row_with_a_new_number_is_dropped_by_itself():
    payload = advice_payload()
    payload["strengthen"][0]["action"] = "跑一次对照，把差值提到 97% 再写进简历"
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert len(advice["strengthen"]) == 1
    assert [row["reason"] for row in rejected] == ["invented_number"]
    assert rejected[0]["table"] == "3.4"


def test_a_table_emptied_by_the_number_check_ends_the_section():
    payload = advice_payload()
    for key in ("structure", "expression", "replace", "counterexample"):
        payload["reuse"][key] = "这句里有原文没有的 99%"
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert advice is None
    assert [row["reason"] for row in rejected][-2:] == ["invented_number", "advice_table_incomplete"]


def test_advice_is_all_or_nothing_across_the_five_tables():
    payload = advice_payload()
    payload["citation"]["breaks"] = ""
    advice, rejected = svc.validate_advice(payload, _StubReport())
    assert advice is None
    assert [row["reason"] for row in rejected] == ["advice_table_incomplete"]


# ------------------------------------------------------------------ 四、面试准备
def test_questions_are_numbered_and_counted_by_the_server():
    items, distribution, rejected = svc.validate_questions(questions_payload(), BODY, 1)
    assert rejected == []
    assert [row["no"] for row in items] == [1, 2, 3, 4, 5]
    assert distribution["total"] == 5
    assert distribution["answerable"] == 3
    assert distribution["weak"] == 1
    assert distribution["high_risk"] == 1
    assert distribution["diagrammed"] == 1
    assert svc.practice_backfill(items) == {"must_practice": "Q4、Q5", "high_risk": "Q5"}


def test_high_risk_without_a_valid_risk_reference_is_downgraded():
    payload = questions_payload([question(status="高危", missing=["阈值"], risk_ref=7)])
    items, distribution, rejected = svc.validate_questions(payload, BODY, 1)
    assert items[0]["status"] == "需补强" and items[0]["risk_ref"] == 0
    assert distribution["high_risk"] == 0 and distribution["weak"] == 1
    assert [row["reason"] for row in rejected] == ["risk_ref_out_of_range"]


def test_weak_status_must_name_what_is_missing():
    items, _, rejected = svc.validate_questions(questions_payload([question(status="需补强")]), BODY, 1)
    assert items == []
    assert [row["reason"] for row in rejected] == ["missing_not_named"]


def test_kind_and_followup_whitelists_are_enforced():
    payload = questions_payload(
        [
            question(kind="八股文"),
            question(question="追问少一条", followups=[{"kind": "为什么", "text": "只有一轮"}]),
            question(
                question="追问标签飘了",
                followups=[{"kind": "为什么", "text": "一"}, {"kind": "灵魂拷问", "text": "二"}],
            ),
            question(question="答案太短", answer="短。"),
        ]
    )
    items, _, rejected = svc.validate_questions(payload, BODY, 1)
    assert items == []
    assert [row["reason"] for row in rejected] == [
        "bad_kind",
        "followup_count",
        "bad_followup_kind",
        "answer_too_short",
    ]


def test_answer_may_not_bring_in_a_new_number():
    long_answer = (
        "这条链路的准确率我们做过对照：同一批样例先跑只靠提示词的版本，再跑适配后的版本，"
        "两边用同一套口径、同一批证据、同一组参数，只有模型版本这一个变量不一样。"
        "看下来差别主要在格式稳定性上，缺段和跑偏少了，内容层面的判断依据还是靠检索给，"
        "我们把检索准确率提到了 97.5% 这一步的代价是多了两天人工标注。"
    )
    items, _, rejected = svc.validate_questions(questions_payload([question(answer=long_answer)]), BODY, 1)
    assert items == []
    assert [row["reason"] for row in rejected] == ["invented_number"]


def test_technical_question_diagram_shape_is_enforced():
    items, distribution, rejected = svc.validate_questions(
        questions_payload([question(diagram=question_diagram())]), BODY, 1
    )
    assert rejected == [] and distribution["diagrammed"] == 1

    thin = dict(question_diagram(), cards=question_diagram()["cards"][:2])
    items, _, rejected = svc.validate_questions(questions_payload([question(diagram=thin)]), BODY, 1)
    assert items == []
    assert [row["reason"] for row in rejected] == ["diagram_incomplete"]


def test_questions_absent_is_not_the_same_as_questions_deferred():
    distribution = svc.questions_distribution([])
    assert distribution["total"] == 0 and distribution["target"] == 20
    assert svc.practice_backfill([]) == {"must_practice": "", "high_risk": ""}
