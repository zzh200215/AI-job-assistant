"""六维项目尺的读法、位次、合计与两条代码判据。

这批测试里**句子形状是从成品反推件里抄的**（那句"30 - 60 分钟缩短至 5 - 10 分钟"
是 PL-02 里基线写得最好的一条），但只取句式不取内容：整段项目原文里带公司/客户信息，
不进仓库（PII 口径见 `docs/upgrade-plan.md`）。
"""

from app.services import project_report_rubric as rubric

GOOD = {"d1_role_signal": 23, "d2_depth": 21, "d3_metric": 14, "d4_transfer": 12, "d5_interview": 12}


def _rows(**override):
    payload = dict(GOOD)
    payload.update(override)
    return rubric.read_dimensions(payload, 1)


def test_six_dims_sum_to_one_hundred_and_five_are_the_project_itself():
    assert rubric.TOTAL_FULL == 100
    assert rubric.BODY_FULL == 95
    assert [row[2] for row in rubric.DIMENSIONS] == [24, 24, 19, 14, 14, 5]


def test_rank_is_a_function_of_position_not_a_model_opinion():
    # 模型给 d6_rank 也没用：那一行是排位的函数。
    rows = rubric.read_dimensions({**GOOD, "d6_rank": 5}, 2)
    row = next(r for r in rows if r["key"] == "d6_rank")
    assert row["score"] == 1
    assert row["positional"] is True
    assert "第 3 位" in row["note"]
    assert [rubric.rank_score(i) for i in (0, 1, 2, 3, 7)] == [5, 3, 1, 1, 1]
    assert [rubric.rank_coefficient(i) for i in (0, 1, 2, 3)] == [5, 3, 1, 1]


def test_total_needs_every_dimension_and_rejects_out_of_range():
    # 五维 23+21+14+12+12 = 82，第 2 位的位次 3 分是服务端加的。
    assert sum(r["score"] for r in _rows() if not r["positional"]) == 82
    assert rubric.total_of(_rows()) == 85
    assert rubric.total_of(_rows(d3_metric=True)) is None
    assert rubric.total_of(_rows(d2_depth=25)) is None  # 越界不夹取
    assert next(r for r in _rows(d2_depth=25) if r["key"] == "d2_depth")["score"] is None
    assert rubric.total_of(_rows(d1_role_signal=-1)) is None


def test_grade_uses_words_not_letters_so_two_reports_cannot_both_say_b():
    assert rubric.grade_of(94) == "标杆级"
    assert rubric.grade_of(85) == "优秀"
    assert rubric.grade_of(75) == "良好"
    assert rubric.grade_of(60) == "需重构"
    assert rubric.grade_of(0) == "暂不可投"
    assert rubric.grade_of(None) is None
    letters = {row[0] for row in rubric.GRADE_BANDS} & {"A", "B", "C", "D"}
    assert letters == set()


def test_persuasion_index_reproduces_the_sample_arithmetic():
    # 思路篇那台实测：(320 + 258 + 83 + 48) ÷ 10 = 70.9
    totals = [(64, 5), (86, 3), (83, 1), (48, 1)]
    assert rubric.persuasion_index(totals) == 70.9
    assert rubric.persuasion_index([(64, 5), (None, 3)]) is None
    assert rubric.persuasion_index([]) is None


def test_share_of_resume_needs_every_peer_scored():
    assert rubric.share_of(85, 3, [(86, 5), (83, 1)]) == round(255 / (255 + 430 + 83) * 100, 1)
    assert rubric.share_of(85, 3, [(None, 5)]) is None
    assert rubric.share_of(None, 3, [(86, 5)]) is None


def test_paired_baseline_survives_a_verb_between_the_two_numbers():
    clause = "常规合同风险扫查初稿由人工约 30 - 60 分钟缩短至 5 - 10 分钟"
    assert rubric.has_paired_value(clause) is True
    assert rubric.metric_gap_clauses(clause) == []


def test_adjective_only_gain_is_the_purist_form_of_the_red_line():
    rows = rubric.metric_gap_clauses("建立标准化审查流程，统一审查判定标准，大幅提升审查效率")
    assert [r["kind"] for r in rows] == ["no_number"]


def test_single_direction_number_is_the_second_form():
    rows = rubric.metric_gap_clauses("对账系统改造后误报率下降 90%")
    assert [r["kind"] for r in rows] == ["single_number"]


def test_declared_pending_value_is_not_counted_as_hidden_gap():
    # 自己写了【待补】的那一条是承认缺口，罚它等于罚诚实。
    assert rubric.metric_gap_clauses("响应耗时降低【待补：按压测路径得到的前后两值】") == []


def test_stack_footprint_splits_slash_parenthetical_writing():
    text = "法规与模板片段入 Milvus / Chroma，风险关系入 Neo4j；条款抽取用 BM25 召回"
    got = rubric.stack_footprint(["Milvus / Chroma", "Neo4j", "BM25", "Redis", "FastAPI"], text)
    assert got["total"] == 5
    assert got["missing"] == ["Redis", "FastAPI"]
    assert got["ratio"] == 0.4


def test_code_judged_red_lines_never_decide_out():
    code_judged, model_judged = rubric.judged_red_line_keys()
    assert set(code_judged) == {"no_baseline", "broken_stack"}
    assert set(model_judged) == {
        "unexplainable_number",
        "others_work",
        "template_smell",
        "not_reproducible",
    }
    assert set(code_judged) | set(model_judged) == set(rubric.RED_LINE_KEYS)


def test_prompt_blocks_are_generated_from_the_tables():
    block = rubric.rubric_prompt_block()
    for key in rubric.DIMENSION_KEYS:
        assert key in block
    assert "不要打分" in block  # D6 那一行明确告诉模型别给分
    assert "六维满分之和 = 100" in block
    red = rubric.red_line_prompt_block()
    assert "无基线的提升" not in red  # 代码判的那条不问模型
    assert "无法复现" in red
    assert "L5" in rubric.difficulty_prompt_block()
