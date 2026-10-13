"""批改稿与面试预演的服务端复核，以及六阶段编排（`resume_report_service`）。

复核这一层守的是同一件事：**模型只能提出，不能自证**。
`del` 命不中原文、改写里冒出简历里没有的数字、题型名飘出白名单——一律带原因拒掉，
而不是静默丢弃或照着渲染上去。
"""

from __future__ import annotations

import json

import pytest

from app.core.security import hash_password
from app.models.user import User
from app.services import resume_report_service as svc
from app.services.resume_blocks import apply_block_edits, build_report_sections
from app.services.resume_report_schema import STAT_MODE_CHANGES, STAT_MODE_OPTIONAL, STAT_MODE_UNCHANGED

SELF_EVAL = "1 年多 AI 应用开发经验，做过法律、金融、电网三个场景"
PROJ = "证据检索准确率约 92%；这套检索是我搭的。证据检索准确率约 92%；这套检索我没搭。"
BASIC = "示例候选人 · 13600000001 · 工作经验：2 年"

SECTIONS = [
    {
        "block_id": "basic",
        "kind": "basic",
        "label": "基本信息",
        "text": BASIC,
        "char_count": len(BASIC),
        "editable": False,
    },
    {
        "block_id": "self_evaluation",
        "kind": "self_evaluation",
        "label": "个人优势",
        "text": SELF_EVAL,
        "char_count": len(SELF_EVAL),
        "editable": True,
    },
    {
        "block_id": "skills",
        "kind": "skills",
        "label": "个人技能",
        "text": "熟悉 LangChain、LlamaIndex，掌握 BM25、RRF",
        "char_count": 28,
        "editable": True,
    },
    {
        "block_id": "proj[0].desc",
        "kind": "project",
        "label": "法律智能体",
        "text": PROJ,
        "char_count": len(PROJ),
        "editable": True,
    },
]
# 数字白名单就是这份简历本身：92、2、1、13600000001 在里面，40 不在。
KNOWN = json.dumps([s["text"] for s in SECTIONS], ensure_ascii=False)

# 库侧那几条用例走的是真链路，`invented_numbers` 的白名单来自 `parsed_json`，
# 所以库里必须真有 BM25 这些带数字的名词——不然口述稿里提一次 BM25 就被判成编造。
PARSED = {
    "name": "示例候选人",
    "phone": "13600000001",
    "self_evaluation": SELF_EVAL,
    "skills": ["LangChain", "BM25", "RRF", "FastAPI"],
    "project_experience": [{"name": "法律智能体平台", "role": "主程", "tech": ["FastAPI"], "desc": PROJ}],
}


def _edit(
    block_id="self_evaluation",
    del_text="做过法律、金融、电网三个场景",
    ins="负责三个场景的检索链路",
    note="面试官会追你负责哪一块，原文没答",
    tier="key",
):
    return {"block_id": block_id, "del": del_text, "ins": ins, "note": note, "tier": tier}


def _reasons(rejected):
    return [item["reason"] for item in rejected]


def test_two_tiers_are_both_kept_and_numbered_in_section_order():
    payload = {
        "edits": [
            _edit(
                block_id="skills",
                del_text="熟悉 LangChain、LlamaIndex",
                ins="LangChain：三个项目全程在用",
                note="LlamaIndex 在项目里对不上",
                tier="normal",
            ),
            _edit(),
        ]
    }

    redline, rejected = svc.validate_redline_edits(SECTIONS, payload, KNOWN)

    assert rejected == []
    assert redline.mode == STAT_MODE_CHANGES
    assert redline.total == 2 and redline.key_total == 1
    # 编号按成稿顺序，不按模型给的顺序。
    assert [(b.block_id, e.mark) for b in redline.blocks for e in b.edits] == [
        ("self_evaluation", 1),
        ("skills", 2),
    ]


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda e: e.update(block_id="proj[9].desc"), "unknown_block"),
        (lambda e: e.update({"del": "简历里没有的那句话"}), "original_mismatch"),
        # 这段在原块里不唯一：写回哪一处都是猜，所以位置不确定的批改一律拒。
        (lambda e: e.update({"del": "证据检索准确率约 92%", "block_id": "proj[0].desc"}), "ambiguous_anchor"),
        (lambda e: e.update({"del": "   "}), "empty_del"),
        (lambda e: e.update(tier="P0"), "bad_tier"),
        (lambda e: e.update(ins="把召回率提到 40%"), "invented_number"),
        (lambda e: e.update(note=""), "empty_note"),
        (lambda e: e.update(note="这一处是硬条件，不达门禁就别投"), "forbidden_word"),
        (lambda e: e.update(note="其余项目照此处理"), "forbidden_word"),
    ],
)
def test_a_single_bad_field_refuses_the_whole_edit(mutate, reason):
    entry = _edit()
    mutate(entry)

    redline, rejected = svc.validate_redline_edits(SECTIONS, {"edits": [entry]}, KNOWN)

    assert _reasons(rejected) == [reason]
    # 只给了一条而且被拒 → 这一段没有出来。折成"零批改"就是让"可以原样投"那句假话上屏。
    assert redline is None


def test_a_todo_span_is_the_legal_exit_for_a_number_nobody_measured():
    entry = _edit(ins="复杂问题跑一半挂掉重来成本高，最大执行步数【待补：实际值】、单步超时 40s")

    redline, rejected = svc.validate_redline_edits(SECTIONS, {"edits": [entry]}, KNOWN)

    assert _reasons(rejected) == ["invented_number"], "只有【待补】里那个数是合法的，裸写的 40 不是"


def test_two_overlapping_anchors_in_one_block_are_refused():
    payload = {
        "edits": [
            _edit(del_text="做过法律、金融、电网三个场景", ins="负责三个场景"),
            _edit(del_text="1 年多 AI 应用开发经验，做过法律、金融、电网三个场景", ins="三个场景的检索链路是我搭的"),
        ]
    }

    redline, rejected = svc.validate_redline_edits(SECTIONS, payload, KNOWN)

    assert _reasons(rejected) == ["overlapping_edit"]
    assert redline.total == 1


def test_the_limit_trims_from_the_end_and_refuses_the_rest_by_name():
    payload = {
        "edits": [
            _edit(),
            _edit(block_id="skills", del_text="掌握 BM25、RRF", ins="BM25 与 RRF 都在用", note="补一句用在哪"),
        ]
    }

    redline, rejected = svc.validate_redline_edits(SECTIONS, payload, KNOWN, limit=1)

    assert redline.total == 1
    assert _reasons(rejected) == ["over_limit"]


def test_an_empty_check_list_is_a_claim_about_the_resume_not_a_failure():
    redline, rejected = svc.validate_redline_edits(
        SECTIONS, {"edits": [], "no_change_note": "这句原本就写得具体，改写反而会把它磨平"}, KNOWN
    )

    assert redline.mode == STAT_MODE_UNCHANGED
    assert redline.free_note == "这句原本就写得具体，改写反而会把它磨平"
    assert rejected == []


def test_only_optional_tiers_read_as_optional_not_as_must_fix():
    redline, _ = svc.validate_redline_edits(SECTIONS, {"edits": [_edit(tier="normal")]}, KNOWN)

    assert redline.mode == STAT_MODE_OPTIONAL
    assert "没有必改项" in redline.stat_sentence()


@pytest.mark.parametrize("payload", [None, [], {"result": "mock"}, "oops"])
def test_an_unparseable_response_is_not_reported_as_a_clean_resume(payload):
    """mock、超时后的简化模板、模型跑偏的返回都长这样。
    把它们折成"这一版可以原样用"，就是让一句假话上屏。"""
    redline, rejected = svc.validate_redline_edits(SECTIONS, payload, KNOWN)

    assert redline is None


def test_a_response_whose_every_edit_was_refused_is_not_a_pass():
    payload = {"edits": [_edit(del_text="简历里没有的那句话"), _edit(block_id="没有这个锚点")]}

    redline, rejected = svc.validate_redline_edits(SECTIONS, payload, KNOWN)

    assert redline is None
    assert len(rejected) == 2


def test_redline_folds_into_the_existing_whole_block_write_path():
    """句级记号只是另一种寻址方式，不是第二条写入路径：折出来的载荷直接喂 `apply_block_edits`。"""
    payload = {
        "edits": [
            _edit(block_id="basic", del_text="工作经验：2 年", ins="工作经验：1 年 8 个月", note="两个数对不上"),
            _edit(),
        ]
    }
    redline, _ = svc.validate_redline_edits(SECTIONS, payload, KNOWN)
    parsed = {"self_evaluation": SELF_EVAL, "skills": ["LangChain"]}

    edits = redline.edits_for_apply()
    new_parsed, applied, rejected = apply_block_edits(parsed, edits)

    # 基本信息那一栏是字段值，批得上但不写回简历。
    assert [e["block_id"] for e in edits] == ["self_evaluation"]
    assert rejected == [] and len(applied) == 1
    assert new_parsed["self_evaluation"] == "1 年多 AI 应用开发经验，负责三个场景的检索链路"
    assert edits[0]["expected_original"] == SELF_EVAL


def test_a_mark_subset_applies_only_what_the_candidate_accepted():
    payload = {
        "edits": [
            _edit(),
            _edit(block_id="skills", del_text="掌握 BM25、RRF", ins="BM25、RRF 都在用", note="补一句用在哪"),
        ]
    }
    redline, _ = svc.validate_redline_edits(SECTIONS, payload, KNOWN)

    only_first = redline.edits_for_apply([1])

    assert [e["block_id"] for e in only_first] == ["self_evaluation"]


def _question(**overrides):
    base = {
        "question": "混合检索里 BM25 和向量检索各自解决什么问题？",
        "kind": "项目深挖",
        "project": "项目 1 · 法律智能体平台",
        "answer": (
            "简单说，BM25 管精确词命中，向量管语义泛化。法律语料里有大量法条编号，向量经常抓不住；"
            "反过来口语描述跟工单用词一个字都不重合，只能靠向量。所以我在法律项目里两路并行召回，"
            "再用 RRF 融合。单用一路的效果我实测过，精确查询或者口语提问总有一半答不好。"
        ),
        "followups": [
            {"kind": "为什么", "text": "为什么不干脆加大向量权重？"},
            {"kind": "权衡/代价", "text": "混合的代价是什么？"},
            {"kind": "边界", "text": "什么场景纯向量就够？"},
        ],
        "status": "可答",
        "missing": [],
    }
    return {**base, **overrides}


def test_a_well_formed_question_passes_and_numbering_is_sequential():
    payload = {"questions": [_question(), _question(question="第二题")]}

    questions, rejected = svc.validate_interview_questions(payload, KNOWN)

    assert rejected == []
    assert [q["no"] for q in questions] == [1, 2]
    assert questions[0]["followups"][1]["kind"] == "权衡/代价"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"kind": "八股"}, "bad_kind"),
        ({"answer": "太短"}, "answer_too_short"),
        (
            {
                "answer": "把召回率从 30% 提到 99.5%，这个数是我自己量的：口径是在那批标注集上逐条判定检索结果有没有命中预设的标准条款，"
                "跑三遍取平均值，每一遍的命中条数都记在评测脚本的输出里，所以对不上也能查是哪一条变了，不是一个拍出来的总数。"
                "这套判定我后来固定成一条规矩，任何指标要进简历之前都得先说清楚它的分母和判定方式是什么。"
            },
            "invented_number",
        ),
        ({"status": "大概能答"}, "bad_status"),
        ({"status": "需补强", "missing": []}, "missing_not_named"),
        ({"followups": [{"kind": "为什么", "text": "一"}]}, "followup_count"),
        (
            {
                "followups": [
                    {"kind": "为什么", "text": "一"},
                    {"kind": "为什么", "text": "二"},
                    {"kind": "薪资谈判", "text": "三"},
                ]
            },
            "bad_followup_kind",
        ),
        (
            {
                "followups": [
                    {"kind": "", "text": "一"},
                    {"kind": "为什么", "text": "二"},
                    {"kind": "为什么", "text": "三"},
                ]
            },
            "bad_followup_kind",
        ),
    ],
)
def test_one_broken_field_refuses_that_question_only(overrides, reason):
    payload = {"questions": [_question(**overrides), _question()]}

    questions, rejected = svc.validate_interview_questions(payload, KNOWN)

    assert _reasons(rejected) == [reason]
    assert len(questions) == 1, "一题不合格不该带走整节"


def test_distribution_is_counted_here_not_reported_by_the_model():
    questions, _ = svc.validate_interview_questions(
        {
            "questions": [
                _question(),
                _question(question="再来一题", kind="对比权衡"),
                _question(question="需补强那题", status="需补强", missing=["清洗前后条数"]),
            ]
        },
        KNOWN,
    )

    distribution = svc.interview_distribution(questions)

    assert distribution["total"] == 3
    assert distribution["by_kind"] == {"项目深挖": 2, "对比权衡": 1}
    assert distribution["by_project"] == {"项目 1 · 法律智能体平台": 3}
    assert distribution["weak"] == 1


def test_apply_strategy_is_read_verbatim_from_the_tree():
    strategy = svc.load_apply_strategy()

    assert strategy is not None
    titles = [chapter["title"] for chapter in strategy["chapters"]]
    assert len(titles) == 5, "第五节规定引用第一至五节，少一节就是文件被改了"
    assert "先诊断" in titles[0]
    assert any("打招呼话术" in chapter["title"] for chapter in strategy["chapters"])
    body = json.dumps(strategy, ensure_ascii=False)
    assert "刚刚活跃" in body and "9:00–11:00" in body


def test_apply_strategy_refuses_to_fake_a_degradation(tmp_path):
    missing = tmp_path / "nope.md"

    assert svc.load_apply_strategy(missing) is None


@pytest.fixture
def report_user(db_session):
    user = User(
        username="report_owner",
        email="report_owner@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _mock_stages(monkeypatch, overview, redline_payload, interview_payload):
    """三发模型调用按 prompt 正文里那句"本次任务"分流，与真实链路同一形状。"""

    def fake_chat(prompt, **kwargs):
        if "批改稿（模块三）" in prompt:
            return redline_payload
        if "面试预演（模块四）" in prompt:
            return interview_payload
        return overview

    monkeypatch.setattr(svc, "chat_json", fake_chat)
    from app.services import resume_analysis_service

    monkeypatch.setattr(resume_analysis_service, "chat_json", fake_chat)


def _overview(dim_scores=(12, 5, 16, 10, 13, 6, 3)):
    keys = [
        "metric_ownership",
        "interview_hooks",
        "role_fit",
        "transferability",
        "project_depth",
        "expression_structure",
        "advantage_section",
    ]
    if dim_scores is None:
        return {"overall_score": 70, "dimensions": {}, "verdict": {}, "competition": {}}
    return {
        "overall_score": 72,
        "dimensions": {
            key: {"score": score, "note": "点名位置的那段话"} for key, score in zip(keys, dim_scores, strict=False)
        },
        "verdict": {"direction": "RAG 应用", "target_level": "中级"},
        "competition": {"positioning_badge": "B 档（中上）", "cards": ["一句话"]},
        "to_next_grade": ["补两处基线"],
    }


def test_the_longest_output_stage_runs_with_thinking_off(db_session, make_resume, report_user, monkeypatch):
    """面试预演是整条链里输出最长的一支。D189 在同一族简历 prompt 上量到：开着思考链
    91.77s / 95.33s 返回的 `content` 长度为 0（8192 token 全花在 reasoning 上），
    空 content 会被判成 provider 失败、整节缺席。所以这一支必须显式关思考链。"""
    rid = make_resume(user_id=report_user.id, parsed_json={"name": "示例候选人", "self_evaluation": SELF_EVAL})
    seen: list[dict] = []

    def spy(prompt, **kwargs):
        if "面试预演（模块四）" in prompt:
            seen.append(kwargs)
            return {"questions": []}
        if "批改稿（模块三）" in prompt:
            return {"edits": [], "no_change_note": ""}
        return _overview()

    monkeypatch.setattr(svc, "chat_json", spy)
    from app.services import resume_analysis_service

    monkeypatch.setattr(resume_analysis_service, "chat_json", spy)

    report = svc.generate_resume_report(db_session, rid, user_id=report_user.id)

    assert seen and seen[0].get("disable_thinking") is True
    assert report.interview is None  # 一题都没过复核，整节缺席，不假装有


def test_the_two_fillins_are_quotes_not_a_new_self_intro():
    """§7 那两处填空由数据层算：标签是"个人优势"的第一句原文，亮点是竞争分析那张牌。
    算在渲染器里的话，应用内那一页就看不到——同一件事两个出处迟早长得不一样。"""
    sections = build_report_sections(
        {"name": "示例候选人", "self_evaluation": "1 年多 AI 应用开发经验。做过法律、金融、电网三个场景"}
    )

    result = svc.build_personalization(sections, {"cards": ["检索链路是我搭的", "另一张"]})

    assert result == {"one_line_label": "1 年多 AI 应用开发经验", "opener": "检索链路是我搭的"}


def test_a_resume_without_an_advantage_section_leaves_the_label_blank_instead_of_inventing_one():
    result = svc.build_personalization([], {"cards": []})

    assert result == {"one_line_label": "", "opener": ""}


def test_the_six_stages_land_in_one_report(db_session, make_resume, report_user, monkeypatch):
    rid = make_resume(user_id=report_user.id, parsed_json=PARSED)
    _mock_stages(
        monkeypatch,
        _overview(),
        {"edits": [_edit()], "no_change_note": ""},
        {"questions": [_question(), _question(question="第二题")]},
    )

    report = svc.generate_resume_report(db_session, rid, user_id=report_user.id)
    data = report.to_public_dict()

    assert report.total_score == 65 and report.grade == "C"
    assert report.redline.total == 1
    assert report.interview["distribution"]["total"] == 2
    assert len(data["apply_strategy"]["chapters"]) == 5
    assert len(data["dimensions"]) == 7
    assert data["report_date"]
    # 对内证据不许出现在候选人视图里。
    for key in ("model_reported_total", "provenance", "stage_errors", "redline_rejected", "interview_rejected"):
        assert key not in data
    assert "model_reported_total" in report.to_internal_dict()


def test_interview_is_deferred_below_the_threshold_and_costs_no_model_call(
    db_session, make_resume, report_user, monkeypatch
):
    rid = make_resume(user_id=report_user.id, parsed_json=PARSED)
    seen: list[str] = []

    def fake_chat(prompt, **kwargs):
        seen.append(prompt)
        if "批改稿（模块三）" in prompt:
            return {"edits": [], "no_change_note": ""}
        if "面试预演（模块四）" in prompt:
            return {"questions": []}
        return _overview((8, 2, 10, 6, 8, 3, 1))  # 合计 38，低于门槛

    monkeypatch.setattr(svc, "chat_json", fake_chat)
    from app.services import resume_analysis_service

    monkeypatch.setattr(resume_analysis_service, "chat_json", fake_chat)

    report = svc.generate_resume_report(db_session, rid, user_id=report_user.id)

    assert report.total_score == 38
    assert report.interview["deferred"] is True
    assert "门禁" not in report.interview["note"] and "阈值" not in report.interview["note"]
    assert not any("面试预演（模块四）" in prompt for prompt in seen), "暂缓那一块不该再花一次模型钱"


def test_a_failing_stage_only_removes_its_own_module(db_session, make_resume, report_user, monkeypatch):
    rid = make_resume(user_id=report_user.id, parsed_json=PARSED)

    def fake_chat(prompt, **kwargs):
        if "批改稿（模块三）" in prompt:
            raise RuntimeError("provider down")
        if "面试预演（模块四）" in prompt:
            return {"questions": [_question()]}
        return _overview()

    monkeypatch.setattr(svc, "chat_json", fake_chat)
    from app.services import resume_analysis_service

    monkeypatch.setattr(resume_analysis_service, "chat_json", fake_chat)

    report = svc.generate_resume_report(db_session, rid, user_id=report_user.id)

    assert report.redline is None
    assert "redline" in report.stage_errors
    assert report.interview["distribution"]["total"] == 1
    assert len(report.dimensions) == 7
    assert "provider down" not in json.dumps(report.to_public_dict(), ensure_ascii=False)


def test_the_report_page_reads_the_same_sections_the_lint_counts(db_session, make_resume, report_user, monkeypatch):
    """`build_report_sections` 是批改稿的版面；不可写回的块也在里面，一段都不许省。"""
    rid = make_resume(
        user_id=report_user.id,
        parsed_json={
            "name": "示例候选人",
            "phone": "13600000001",
            "self_evaluation": SELF_EVAL,
            "skills": ["LangChain"],
            "work_experience": [
                {
                    "company": "上海合提",
                    "title": "AI 应用开发",
                    "start": "2024.11",
                    "end": "至今",
                    "desc": "负责检索链路",
                }
            ],
            "project_experience": [
                {"name": "法律智能体平台", "role": "主程", "tech": ["FastAPI"], "desc": "构建 Agentic RAG"}
            ],
        },
    )
    _mock_stages(monkeypatch, _overview(), {"edits": [], "no_change_note": ""}, {"questions": []})

    report = svc.generate_resume_report(db_session, rid, user_id=report_user.id)

    kinds = [block["kind"] for block in report.sections]
    assert kinds == [
        "basic",
        "self_evaluation",
        "skills",
        "work_header",
        "work",
        "project_header",
        "project_tech",
        "project",
        "education",
    ]
    assert [b["editable"] for b in report.sections] == [False, True, True, False, True, False, False, True, False]
