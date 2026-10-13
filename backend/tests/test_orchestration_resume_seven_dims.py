"""编排里那一发简历诊断换成七维表之后的四条承重（§10.41 他点的 ③）。

改之前的形状是这样的：`AGENT_REPORT_PROMPT` 从没要求过 `resume_diagnosis` 这个键，
而「智能分析」那一屏读的是 `summaryReport.resume_diagnosis.score`——
真 provider 下那一格**永远是空白**，只有 mock 载荷里写着 78，于是演示看起来像"有数"。
同一份简历的另一半（六模块评估报告）走的是七维定权相加。两条口径并存、且其中一条根本没数据，
这一族最贵的错法就是这种"画得出来但来源不存在"。

现在钉四条：
1. `ResumeAgent` 的分数与等级由服务端按七维相加，与评估报告同一把尺、同一个读法；
2. 缺维度是"未评分"，不是 0 分（总分随之未知，绝不借完整度分顶上）；
3. 汇总报告里那一格由服务端折出来，模型若自己写了一个 `resume_diagnosis` 会被覆盖掉；
4. 那一步没跑 ⇒ 键整个不存在，前端拿到的不是空壳。
"""

from __future__ import annotations

import copy

from app.agents.resume_agent import ResumeAgent
from app.agents.summary_agent import SummaryAgent, resume_diagnosis_from
from app.orchestration.context import AgentContext
from app.prompts.resume_agent import RESUME_AGENT_PROMPT
from app.services import llm_service
from app.services import resume_report_rubric as rubric

# 与 `_MOCK_REPORT_OVERVIEW` 同一组数：演示态下两屏读到的必须是同一个总分与同一档。
EXPECTED_SUM = 12 + 5 + 16 + 10 + 13 + 6 + 3


def _context(db, resume_id: int) -> AgentContext:
    return AgentContext(resume_id=resume_id, jd_id=0, db=db)


def _user(db) -> int:
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        username="orch_seven_dims",
        email="orch_seven_dims@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    return user.id


# ---------------------------------------------------------------- 1 / 2 ResumeAgent


def test_resume_agent_scores_on_the_same_seven_dimension_rubric(db_session, make_resume):
    rid = make_resume(user_id=_user(db_session), parsed_json=llm_service._MOCK_RESUME)

    result = ResumeAgent().run_impl(_context(db_session, rid))

    assert [row["key"] for row in result["dimensions"]] == [d[0] for d in rubric.DIMENSIONS]
    assert result["total_score"] == EXPECTED_SUM
    assert result["grade"] == rubric.grade_of(EXPECTED_SUM)
    # 旧那两格自由分出树：屏幕上没人读它们，留着就是第三把尺。
    assert "format_score" not in result and "expression_quality" not in result


def test_resume_agent_hands_the_model_the_generated_rubric_block(db_session, make_resume, monkeypatch):
    """表改了 prompt 没跟着走，就该在这里红，而不是等某个人手抄一份进 prompt。"""
    seen: list[str] = []

    def spy(prompt, **kwargs):
        seen.append(prompt)
        # 深拷贝：`run_impl` 会往返回的那份 dict 里写 dimensions/total_score，
        # 直接交模块级载荷就会被永久改写（这一族在 mock 派发上摔过一次）。
        return copy.deepcopy(llm_service._MOCK_AGENT_RESUME)

    monkeypatch.setattr(llm_service, "chat_json", lambda prompt, **kw: spy(prompt, **kw))
    monkeypatch.setattr("app.agents.resume_agent.chat_json", spy)
    rid = make_resume(user_id=_user(db_session), parsed_json={"name": "张三"})

    ResumeAgent().run_impl(_context(db_session, rid))

    assert seen and rubric.rubric_prompt_block() in seen[0]
    assert "不要自己写总分或等级" in seen[0]


def test_a_missing_dimension_is_unknown_not_zero(db_session, make_resume, monkeypatch):
    """少一维 ⇒ 总分未知、等级未知；这一格在屏上写"未评分"，不借完整度分顶上。"""
    payload = {
        "basic_info": {"name": "张三"},
        "dimensions": {
            "role_fit": {"score": 16, "note": "（mock）方向标签要读完整份简历"},
            "metric_ownership": {"score": 2},
        },
        "weaknesses": [],
    }
    monkeypatch.setattr("app.agents.resume_agent.chat_json", lambda prompt, **kw: payload)
    rid = make_resume(user_id=_user(db_session), parsed_json={"name": "张三"})

    result = ResumeAgent().run_impl(_context(db_session, rid))

    assert result["total_score"] is None
    assert result["grade"] is None
    assert [row["score"] for row in result["dimensions"]].count(None) == 5


# ---------------------------------------------------------------- 3 / 4 汇总那一格


def _resume_result_stub(**overrides):
    stub = {
        "basic_info": {"name": "张三"},
        "dimensions": rubric.read_dimensions(llm_service._MOCK_AGENT_RESUME["dimensions"]),
        "total_score": EXPECTED_SUM,
        "grade": "C",
        "weaknesses": [],
    }
    stub.update(overrides)
    return stub


def test_key_findings_only_collect_the_dimensions_below_sixty_percent():
    diagnosis = resume_diagnosis_from(_resume_result_stub())

    assert diagnosis["total_score"] == EXPECTED_SUM and diagnosis["grade"] == "C"
    labels = [row["label"] for row in diagnosis["dimensions"] if row["score"] < row["full"] * 0.6]
    assert len(diagnosis["key_findings"]) == len(labels)
    assert all(any(label in line for label in labels) for line in diagnosis["key_findings"])
    assert "七维" in diagnosis["scale_note"]


def test_the_summary_composes_the_cell_and_overwrites_the_models_claim(db_session, make_resume, monkeypatch):
    """模型自己写一个 `resume_diagnosis.score` 也不能上屏：那一格只有服务端折的这一个来源。"""
    context = _context(db_session, make_resume(user_id=_user(db_session), parsed_json=llm_service._MOCK_RESUME))
    context.agent_outputs["ResumeAgent"] = _resume_result_stub()

    monkeypatch.setattr(
        "app.agents.summary_agent.chat_json",
        lambda prompt, **kw: {"report_title": "汇总", "resume_diagnosis": {"score": 99}},
    )

    result = SummaryAgent().run_impl(context)

    assert result["resume_diagnosis"]["total_score"] == EXPECTED_SUM
    assert "score" not in result["resume_diagnosis"], "模型自报的那一位必须被整块覆盖"


def test_a_run_without_the_diagnosis_step_leaves_no_empty_shell(db_session, monkeypatch):
    context = _context(db_session, 0)
    monkeypatch.setattr(
        "app.agents.summary_agent.chat_json",
        lambda prompt, **kw: {"report_title": "汇总", "resume_diagnosis": {"score": 99, "key_findings": []}},
    )

    result = SummaryAgent().run_impl(context)

    assert "resume_diagnosis" not in result, "那一步没跑就该整格不出现，而不是给一个假的 99"


# ---------------------------------------------------------------- 5 mock 与派发形状


def test_mock_dispatch_still_routes_the_diagnosis_prompt_to_the_agent_payload():
    """派发关键字「资深简历诊断专家」还在，且新的七维载荷真能过 `read_dimensions`。"""
    from app.prompts.rendering import render_prompt

    prompt = render_prompt(
        RESUME_AGENT_PROMPT,
        resume_json="{}",
        rubric_block=rubric.rubric_prompt_block(),
    )
    payload = llm_service._mock_chat(prompt)

    assert "dimensions" in payload
    assert "format_score" not in payload
    rows = rubric.read_dimensions(llm_service._MOCK_AGENT_RESUME["dimensions"])
    assert rubric.total_of(rows) == EXPECTED_SUM
