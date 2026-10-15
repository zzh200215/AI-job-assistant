"""第三把尺：组合六维、位次区间、覆盖结论、共用栈、换皮比对。

这一族的测试只钉三件事：
* **数对得上参考件**——`[0,1,2]` 这一组占第 1~3 位、参考件那一维写 4 分，
  按参考件那五个分喂进去要能复现合计 94；
* **凡是能算的都不许由模型自证**——覆盖结论由格子推、共用栈由交集算、
  均分只算跑过的那几份；
* **两条故意的不对齐要一直可见**——组合的评级档位与单项目不同名同值不同区间，
  难度档位不认参考件写的 "L5+"。
"""

from __future__ import annotations

from app.services import portfolio_report_rubric as rubric
from app.services import project_report_rubric as single
from tests.portfolio_report_payloads import FIRST_DESC, SECOND_DESC, THIRD_DESC


def test_六维满分与参考件那张表一致():
    assert [row[2] for row in rubric.DIMENSIONS] == [24, 24, 19, 14, 14, 5]
    assert rubric.TOTAL_FULL == 100
    assert rubric.BODY_FULL == 95
    assert len(rubric.MODEL_JUDGED_KEYS) == 5
    assert [row[0] for row in rubric.DIMENSIONS if not row[3]] == ["d6_rank_span"]


def test_维度名是组合口径不是单项目那把():
    labels = " ".join(row[1] for row in rubric.DIMENSIONS)
    assert "组合区分度与真实感" in labels
    assert "技术纵深与迁移" in labels
    # 单项目那把里 D2 叫"深度与真实感"：两把尺的 D2 不是同一个量。
    assert single.dimension_label("d2_depth") != rubric.dimension_label("d2_combo_distinct")


def test_位次区间那一维复现参考件的那个四分():
    assert rubric.span_of([0, 1, 2]) == (1, 3)
    assert rubric.span_score([0, 1, 2]) == 4
    assert rubric.span_score([0, 1]) == 4
    assert rubric.span_score([1, 2]) == 2
    # 第三位及以后本来就是 1 分，再扣也不许掉到 0——0 分意味着"这一组没占位"。
    assert rubric.span_score([2, 3]) == 1
    assert "第 1~3 位" in rubric.span_note([0, 1, 2])
    assert "第 2 位" in rubric.span_note([1])


def test_合计九十四落进优秀而不是标杆级():
    raw = {
        "d1_role_signal": {"score": 24, "note": "x"},
        "d2_combo_distinct": {"score": 21, "note": "y"},
        "d3_metric": {"score": 18, "note": "z"},
        "d4_growth_line": {"score": 13, "note": "w"},
        "d5_interview": {"score": 14, "note": "v"},
    }
    rows = rubric.read_dimensions(raw, [0, 1, 2])
    assert len(rows) == 6
    assert rubric.total_of(rows) == 94
    assert rubric.grade_of(94) == "优秀"
    # 这一条钉的是**故意的不对齐**：同一分数在单项目那把尺里叫标杆级。
    assert single.grade_of(94) == "标杆级"


def test_缺一个维度就不给总分():
    rows = rubric.read_dimensions({"d1_role_signal": {"score": 20}}, [0, 1])
    assert rubric.total_of(rows) is None
    assert rubric.grade_of(None) is None


def test_评级档位区间自己切且不留缝():
    assert rubric.grade_of(95) == "标杆级"
    assert rubric.grade_of(88) == "优秀"
    assert rubric.grade_of(87) == "良好"
    assert rubric.grade_of(75) == "良好"
    assert rubric.grade_of(74) == "需重组"
    assert rubric.grade_of(60) == "需重组"
    assert rubric.grade_of(59) == "暂不可投"
    assert "需重组" in rubric.grade_scale_block()


def test_难度档位沿用那五档且不认参考件的加号():
    for level in ("L1", "L2", "L3", "L4", "L5"):
        assert rubric.is_known_difficulty(level)
    # 参考件表头写的是 "L5+"：树里没有加号这一档，白名单不扩（规范里点名这条不对齐）。
    assert not rubric.is_known_difficulty("L5+")
    assert not rubric.is_known_difficulty("很难")


def test_均分只算跑过的那几份():
    assert rubric.average_of([95, 97, 95]) == 95.7
    assert rubric.average_of([95, 97, None]) == 96.0
    assert rubric.average_of([None, None]) is None
    assert rubric.average_of([]) is None


def test_覆盖结论由格子推模型不参与():
    full_all = {0: "重点覆盖", 1: "重点覆盖", 2: "重点覆盖"}
    assert rubric.coverage_verdict(full_all, 3)["word"] == "极强"
    two = {0: "重点覆盖", 1: "重点覆盖", 2: "部分覆盖"}
    assert rubric.coverage_verdict(two, 3)["word"] == "强"
    one = {0: "重点覆盖", 1: "部分覆盖", 2: "未覆盖"}
    verdict = rubric.coverage_verdict(one, 3)
    assert verdict["word"] == "强"
    assert verdict["full"] == [0]
    partial_only = {0: "部分覆盖", 1: "未覆盖", 2: "未覆盖"}
    assert rubric.coverage_verdict(partial_only, 3)["word"] == "中"
    assert rubric.coverage_verdict({0: "未覆盖", 1: "未覆盖"}, 2)["word"] == "未覆盖"


def test_格子三种写法都认():
    assert rubric.normalize_cell("●") == rubric.COVER_FULL
    assert rubric.normalize_cell("○") == rubric.COVER_PARTIAL
    assert rubric.normalize_cell("部分") == rubric.COVER_PARTIAL
    assert rubric.normalize_cell("大概覆盖") == rubric.COVER_NONE
    assert rubric.COVERAGE_MARKS[rubric.COVER_NONE] == ""


def test_覆盖表拒掉白名单外与不完整的提名():
    raw = [
        {
            "capability": "hybrid_retrieval",
            "cells": [{"project_index": 0, "cell": "●"}, {"project_index": 1, "cell": "○"}],
        },
        {"capability": "区块链存证", "cells": [{"project_index": 0, "cell": "●"}, {"project_index": 1, "cell": "●"}]},
        {"capability": "knowledge_graph", "cells": [{"project_index": 0, "cell": "●"}]},
        {
            "capability": "hybrid_retrieval",
            "cells": [{"project_index": 0, "cell": "●"}, {"project_index": 1, "cell": "●"}],
        },
        {"capability": "llmops", "cells": [{"project_index": 0, "cell": "●"}, {"project_index": 5, "cell": "●"}]},
    ]
    rows, dropped = rubric.clean_capability_rows(raw, [0, 1])
    assert [row["key"] for row in rows] == ["hybrid_retrieval"]
    reasons = [row["reason"] for row in dropped]
    assert "capability_off_list" in reasons
    assert "cells_incomplete" in reasons
    assert "capability_duplicate" in reasons
    assert "cells_incomplete" in reasons  # 序号 5 不在选中集里，也算列不齐


def test_共用栈是交集不是模型提名():
    stack = rubric.stack_reuse(
        {0: ["LangGraph", "Chroma", "FastAPI"], 1: ["fastapi", "MySQL"], 2: ["Chroma / Milvus", "Qwen"]}
    )
    # FastAPI 在两个项目里（一个写 "FastAPI" 一个写小写，是同一只）、Chroma 在两个里
    # （第三个写成 "Chroma / Milvus" 并列，要拆开算）。
    assert set(stack["shared"]) == {"FastAPI", "Chroma"}
    assert stack["shared_count"] == 2
    # 上屏用的是原文里那个写法，不是折叠形——把 FastAPI 画成 fastapi 会让人以为是另一只组件。
    assert "Milvus" in stack["unique_by_index"]["2"]
    assert stack["shared_ratio"] is not None and stack["shared_ratio"] < 1

    claim = rubric.model_claimed_shared(["FastAPI", "Kafka", "LangGraph"], stack["shared"])
    assert [name.lower() for name in claim["kept"]] == ["fastapi"]
    assert set(claim["dropped"]) == {"Kafka", "LangGraph"}


def test_完全相同才算换皮那一刀近似只出证据():
    texts = {0: FIRST_DESC, 1: SECOND_DESC, 2: THIRD_DESC}
    assert rubric.duplicate_pairs(texts) == []
    assert rubric.near_copy_pairs(texts) == []
    ratio = rubric.pair_similarity(FIRST_DESC, SECOND_DESC)
    assert ratio < 0.3

    # 只改标点与空白 = 同一个项目换个名字：出局形状。
    spaced = SECOND_DESC.replace("。", " 。 ").replace("\n", "\n  ").replace("，", " ， ")
    hits = rubric.duplicate_pairs({0: SECOND_DESC, 1: spaced})
    assert hits and hits[0]["kind"] == "identical"

    # 只在句末多打一个字：差一个字就不是"逐字相同"，**不该**算 identical。
    # 这一条是那条红线的假阳性边界——真简历里两个项目正文相近是常态，判成换皮就把门做坏了。
    one_char = SECOND_DESC.rstrip() + "了"
    assert rubric.duplicate_pairs({0: SECOND_DESC, 1: one_char}) == []
    assert rubric.near_copy_pairs({0: SECOND_DESC, 1: one_char})[0]["kind"] == "near_copy"

    # 只在末尾改一个数字：近似雷同（有假阳性风险，所以只出证据、不出局）。
    tweaked = SECOND_DESC.replace("15 分钟", "12 分钟")
    near = rubric.near_copy_pairs({0: SECOND_DESC, 1: tweaked})
    assert near and near[0]["kind"] == "near_copy"
    assert rubric.duplicate_pairs({0: SECOND_DESC, 1: tweaked}) == []


def test_红线里只有一条代码判的够格出局():
    code_keys, model_keys = rubric.judged_red_line_keys()
    assert code_keys == ("duplicate_projects",)
    assert set(model_keys) == {"others_work_combo", "no_growth_line", "unanswerable_combo"}
    assert rubric.rejecting_code_red_line("duplicate_projects")
    assert not rubric.rejecting_code_red_line("others_work_combo")
    assert set(rubric.RED_LINE_KEYS) == set(code_keys) | set(model_keys)


def test_补齐后预计要点名某一维():
    assert rubric.mentions_dimension("组合 D3 指标责任这一维站得住")
    assert rubric.mentions_dimension("D2 更稳")
    assert rubric.mentions_dimension("叙事顺序也看得清了")
    assert not rubric.mentions_dimension("整体更完整，更好看")


def test_横向对比与轮次与题型的白名单形状():
    assert len(rubric.COMPARE_ROWS) == 7
    assert rubric.COMPARE_ROW_LABELS["skeleton"] == "核心骨架"
    assert len(rubric.INTERVIEW_ROUNDS) == 5
    assert set(rubric.DECISIVE_ROUNDS) <= set(rubric.INTERVIEW_ROUND_KEYS)
    assert len(rubric.CAPABILITIES) == 12
    assert len(rubric.QUESTION_KINDS) == 6
    assert rubric.TARGET_QUESTION_COUNT == 12


def test_prompt里的表由代码生成不手抄():
    block = rubric.rubric_prompt_block()
    assert "六维满分之和 = 100" in block
    assert "不要打分" in block
    red = rubric.red_line_prompt_block()
    # 代码自算的那一条不该出现在要模型提名的表里。
    assert "duplicate_projects" not in red
    assert "others_work_combo" in red
    assert len(rubric.difficulty_prompt_block().splitlines()) == 5
