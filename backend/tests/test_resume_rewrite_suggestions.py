"""B1.2: rewrite suggestions must be unable to say anything unanchored.

The model is asked to rewrite only the text it was given, per block id. These
tests cover the gate that turns "the model said so" into "this is a real line of
this candidate's CV", because anything that passes the gate becomes an editable
sentence in someone's resume.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import resume as resume_api
from app.api.auth import get_current_user
from app.api.resume import router as resume_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.user import User
from app.services import resume_rewrite_service as svc
from app.services import rewrite_job_service as job_service
from app.services.match_score_service import canonical_match_score, resume_version_of
from app.services.resume_blocks import build_resume_blocks
from app.services.scoring_config import SCORE_METHOD

PARSED = {
    "name": "张三",
    "skills": ["Python", "FastAPI"],
    "self_evaluation": "三年后端开发经验",
    "work_experience": [
        {"company": "A 公司", "title": "后端工程师", "start": "2021-03", "end": "至今", "desc": "负责订单服务"}
    ],
    "project_experience": [],
}


def _blocks():
    return build_resume_blocks(PARSED)


def _suggestion(
    block_id="self_evaluation", original="三年后端开发经验", proposed="三年后端开发经验，专注订单链路", **extra
):
    return {"block_id": block_id, "original": original, "proposed_text": proposed, "reason": "把已有事实写清楚"} | extra


# ---------------------------------------------------------------- the gate


def test_a_well_formed_suggestion_passes():
    accepted, rejected = svc.validate_rewrite_suggestions(_blocks(), {"suggestions": [_suggestion()]})

    assert [s["block_id"] for s in accepted] == ["self_evaluation"]
    assert accepted[0]["original"] == "三年后端开发经验"
    assert accepted[0]["kind"] == "self_evaluation"
    assert rejected == []


def test_an_invented_anchor_is_refused():
    accepted, rejected = svc.validate_rewrite_suggestions(
        _blocks(), {"suggestions": [_suggestion(block_id="work[9].desc", original="负责订单服务")]}
    )

    assert accepted == []
    assert rejected == [{"block_id": "work[9].desc", "reason": "unknown_block"}]


def test_a_paraphrased_original_is_refused():
    """The model restating a different line as "original" would make the 原文→改后
    panel show a sentence the candidate never wrote."""
    accepted, rejected = svc.validate_rewrite_suggestions(
        _blocks(), {"suggestions": [_suggestion(original="我有三年后端经验")]}
    )

    assert accepted == []
    assert rejected[0]["reason"] == "original_mismatch"


def test_only_the_first_suggestion_per_anchor_survives():
    accepted, rejected = svc.validate_rewrite_suggestions(
        _blocks(), {"suggestions": [_suggestion(), _suggestion(proposed="另一种改法")]}
    )

    assert len(accepted) == 1
    assert rejected == [{"block_id": "self_evaluation", "reason": "duplicate_block"}]


def test_noop_and_runaway_proposals_are_refused():
    # The ceiling for an 8-character block is len+120, so the runaway case has to clear that.
    accepted, rejected = svc.validate_rewrite_suggestions(
        _blocks(),
        {
            "suggestions": [
                _suggestion(proposed="三年后端开发经验"),
                _suggestion(proposed="超长" * 70),
            ]
        },
    )

    assert accepted == []
    assert [r["reason"] for r in rejected] == ["unchanged", "proposal_too_long"]


def test_over_limit_across_distinct_anchors_is_marked():
    blocks = build_resume_blocks(
        {
            "self_evaluation": "评价",
            "work_experience": [
                {"company": "A", "title": "T", "desc": "描述一"},
                {"company": "B", "title": "U", "desc": "描述二"},
            ],
        }
    )
    payload = {
        "suggestions": [
            {"block_id": "self_evaluation", "original": "评价", "proposed_text": "改后评价"},
            {"block_id": "work[0].desc", "original": "描述一", "proposed_text": "改后一"},
            {"block_id": "work[1].desc", "original": "描述二", "proposed_text": "改后二"},
        ]
    }

    accepted, rejected = svc.validate_rewrite_suggestions(blocks, payload, limit=2)

    assert [a["block_id"] for a in accepted] == ["self_evaluation", "work[0].desc"]
    assert rejected == [{"block_id": "work[1].desc", "reason": "over_limit"}]


def test_a_response_that_is_not_a_list_is_refused_wholesale():
    for payload in ({"suggestions": "oops"}, {"nope": []}, None, "建议如下"):
        accepted, rejected = svc.validate_rewrite_suggestions(_blocks(), payload)
        assert accepted == []
        assert rejected == [{"block_id": None, "reason": "malformed_response"}], payload


def test_a_bare_array_is_accepted_so_no_suggestion_is_lost_to_shape():
    accepted, rejected = svc.validate_rewrite_suggestions(
        _blocks(), [_suggestion(proposed="三年后端开发经验，专注订单链路")]
    )

    assert [s["block_id"] for s in accepted] == ["self_evaluation"]
    assert rejected == []


# ---------------------------------------------------------------- the service


@pytest.fixture
def actor(db_session):
    user = User(
        username="rw_user", email="rw_user@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    other = User(
        username="rw_other", email="rw_other@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    db_session.add_all([user, other])
    db_session.commit()
    return user, other


def _resume_row(db, user, parsed=None):
    row = Resume(
        user_id=user.id,
        name="改写验证简历",
        file_name="rw.pdf",
        file_path="uploads/rw.pdf",
        file_type="pdf",
        file_size=2048,
        parsed_json=parsed if parsed is not None else dict(PARSED),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job_row(db, user):
    row = JobDescription(
        user_id=user.id,
        title="高级后端工程师",
        company="示例公司",
        raw_text="高级后端工程师",
        is_active=1,
        parsed_json={"title": "高级后端工程师", "required_skills": ["Python", "MySQL"], "nice_to_have": []},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_an_unparseable_resume_never_costs_an_llm_call(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user, parsed={"name": "张三"})
    calls = []
    monkeypatch.setattr(svc, "chat_json", lambda prompt, **kw: calls.append(prompt) or {})

    result = svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    assert calls == []
    assert result["suggestions"] == []
    assert "没有可供改写的文本块" in result["note"]


def test_suggestions_never_touch_the_stored_resume(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user)
    before = json.dumps(resume.parsed_json, ensure_ascii=False, sort_keys=True)
    monkeypatch.setattr(
        svc,
        "chat_json",
        lambda prompt, **kw: {"suggestions": [_suggestion(proposed="三年后端开发经验，专注高并发订单链路")]},
    )

    result = svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    assert len(result["suggestions"]) == 1
    db_session.expire_all()
    assert json.dumps(db_session.get(Resume, resume.id).parsed_json, ensure_ascii=False, sort_keys=True) == before


def test_the_prompt_carries_anchors_inside_a_data_boundary(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user)
    prompts = []
    monkeypatch.setattr(svc, "chat_json", lambda prompt, **kw: prompts.append(prompt) or {"suggestions": []})

    svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    prompt = prompts[0]
    assert "work[0].desc" in prompt
    assert "<resume_blocks" in prompt  # candidate text is data, never instructions
    assert "prompt-render-v1" in prompt


def test_the_rewrite_call_is_the_one_arm_that_turns_thinking_off(db_session, actor, monkeypatch):
    """② 的落点就在这一发，而且**只有**这一发：这一发同步等 LLM，D189 量到开着思考链时
    91.77s / 95.33s 返回的 `content` 长度是 0，D195 关掉后 10.68s 出 3 条通过校验的建议。
    其余 `chat_json` 调用方必须继续用默认那一臂（反向证据由 provider 契约测试钉住）。"""
    user, _ = actor
    resume = _resume_row(db_session, user)
    seen = {}

    def fake_chat(prompt, **kwargs):
        seen.update(kwargs)
        return {"suggestions": []}

    monkeypatch.setattr(svc, "chat_json", fake_chat)

    svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    assert seen == {"disable_thinking": True}


def test_cross_user_resume_and_missing_job_are_refused(db_session, actor, monkeypatch):
    user, other = actor
    resume = _resume_row(db_session, user)
    job = _job_row(db_session, other)
    monkeypatch.setattr(svc, "chat_json", lambda prompt, **kw: {"suggestions": []})

    with pytest.raises(ValueError):
        svc.build_rewrite_suggestions(db_session, resume.id, user_id=other.id)

    with pytest.raises(ValueError):
        svc.build_rewrite_suggestions(db_session, resume.id, jd_id=999999, user_id=user.id)

    # A job owned by someone else is not a valid rewrite target either.
    with pytest.raises(ValueError):
        svc.build_rewrite_suggestions(db_session, resume.id, jd_id=job.id, user_id=user.id)


# ---------------------------------------------------------------- wiring


def test_the_job_endpoints_are_registered_and_the_sync_one_is_gone():
    app = FastAPI()
    app.include_router(resume_router, prefix="/resume")
    paths = {route.path for route in app.routes}

    assert "/resume/{resume_id}/rewrite-suggestion-jobs" in paths
    assert "/resume/rewrite-suggestion-jobs/{job_id}" in paths
    # 同步那一发必须真的出树。留着它就是两条路径写同一件事——这仓库反复记过的那种分叉源。
    assert "/resume/{resume_id}/rewrite-suggestions" not in paths


def test_the_job_round_trip_reports_rejected_anchors_to_the_client(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user)
    monkeypatch.setattr(
        svc,
        "chat_json",
        lambda prompt, **kw: {
            "suggestions": [
                _suggestion(proposed="三年后端开发经验，主导过订单链路重构"),
                _suggestion(block_id="work[3].desc", original="不存在"),
            ]
        },
    )
    # POST 只负责投递；起跑由下面那一行代做，走的是**同一个** `run_job_on`，
    # 不是测试里另写一份"看起来一样"的执行逻辑。
    monkeypatch.setattr(resume_api, "submit_rewrite_job", lambda job_id: None)

    with TestClient(_resume_client(db_session, user)) as client:
        posted = client.post(f"/resume/{resume.id}/rewrite-suggestion-jobs", json={}).json()
        assert posted["code"] == 0
        assert posted["data"]["status"] == "pending"
        job_id = posted["data"]["job_id"]

        assert job_service.run_job_on(db_session, job_id) is True

        body = client.get(f"/resume/rewrite-suggestion-jobs/{job_id}").json()

    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert len(body["data"]["suggestions"]) == 1
    assert body["data"]["rejected"][0]["reason"] == "unknown_block"
    # 轮询载荷里不许出现失败原因那句话：它可能带模型返回的内容，而这是对外端点。
    assert "error_msg" not in body["data"]


# ---------------------------------------------------------------- applying


def _resume_client(db, user):
    app = FastAPI()
    app.include_router(resume_router, prefix="/resume")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_apply_writes_the_new_text_back_and_moves_the_version(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    before_version = resume_version_of(resume)

    result = svc.apply_rewrite_suggestions(
        db_session,
        resume.id,
        [
            {
                "block_id": "self_evaluation",
                "proposed_text": "三年后端开发经验，专注订单链路",
                "expected_original": "三年后端开发经验",
            }
        ],
        user_id=user.id,
    )
    db_session.expire_all()

    assert result["changed"] is True
    assert result["applied"][0]["before"] == "三年后端开发经验"
    assert result["resume_version"] != before_version
    fresh = db_session.get(Resume, resume.id)
    assert fresh.parsed_json["self_evaluation"] == "三年后端开发经验，专注订单链路"
    assert fresh.parsed_json["work_experience"][0]["desc"] == "负责订单服务"  # untouched blocks stay


def test_a_stale_anchor_is_refused_instead_of_overwriting_newer_text(db_session, actor):
    """Anchors are positional. If the candidate changed the resume after the
    suggestions were generated, applying by block_id would clobber their edit."""
    user, _ = actor
    resume = _resume_row(db_session, user)
    resume.parsed_json = {**resume.parsed_json, "self_evaluation": "候选人自己改过的版本"}
    db_session.add(resume)
    db_session.commit()

    stale = svc.apply_rewrite_suggestions(
        db_session,
        resume.id,
        [{"block_id": "self_evaluation", "proposed_text": "覆盖掉新写的东西", "expected_original": "三年后端开发经验"}],
        user_id=user.id,
    )

    assert stale["changed"] is False
    assert stale["rejected"][0]["reason"] == "stale_anchor"
    db_session.expire_all()
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "候选人自己改过的版本"


def test_rejected_only_edits_persist_nothing(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    before = resume_version_of(resume)

    result = svc.apply_rewrite_suggestions(
        db_session, resume.id, [{"block_id": "work[8].desc", "proposed_text": "幻觉"}], user_id=user.id
    )

    assert result["changed"] is False
    assert result["resume_version"] == before
    assert db_session.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).count() == 0


def test_apply_keeps_a_snapshot_that_can_undo_it(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)

    result = svc.apply_rewrite_suggestions(
        db_session,
        resume.id,
        [{"block_id": "work[0].desc", "proposed_text": "负责订单服务，日均 500 万单的稳定性 owner"}],
        user_id=user.id,
    )

    snapshot = db_session.get(ResumeVersion, result["snapshot_version_id"])
    assert snapshot.format == "json"
    assert json.loads(snapshot.content)["work_experience"][0]["desc"] == "负责订单服务"
    assert snapshot.change_log[0]["block_id"] == "work[0].desc"


def test_apply_recomputes_the_match_score_for_the_target_job(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    job = _job_row(db_session, user)

    baseline = canonical_match_score(db_session, resume, job, user_id=user.id, persist=False)["score"]

    result = svc.apply_rewrite_suggestions(
        db_session,
        resume.id,
        [{"block_id": "skills", "proposed_text": "Python、FastAPI、MySQL、Redis、消息队列"}],
        jd_id=job.id,
        user_id=user.id,
    )

    assert result["score"]["before"]["score"] == baseline
    assert result["score"]["delta"] is not None and result["score"]["delta"] > 0
    assert result["score"]["after"]["method"] == SCORE_METHOD


def test_apply_respects_ownership(db_session, actor):
    user, other = actor
    resume = _resume_row(db_session, user)

    with pytest.raises(ValueError):
        svc.apply_rewrite_suggestions(
            db_session, resume.id, [{"block_id": "self_evaluation", "proposed_text": "别人的简历"}], user_id=other.id
        )


def test_the_apply_endpoint_persists_through_http(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)

    with TestClient(_resume_client(db_session, user)) as client:
        body = client.post(
            f"/resume/{resume.id}/apply-rewrites",
            json={"edits": [{"block_id": "self_evaluation", "proposed_text": "三年后端开发经验，专注高并发"}]},
        ).json()

    assert body["code"] == 0
    assert body["data"]["changed"] is True
    db_session.expire_all()
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "三年后端开发经验，专注高并发"


def test_the_apply_endpoint_rejects_an_empty_edit_list(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)

    with TestClient(_resume_client(db_session, user)) as client:
        body = client.post(f"/resume/{resume.id}/apply-rewrites", json={"edits": []}).json()

    assert body["code"] != 0
    assert "edits" in body["message"]


# ---------------------------------------------------------------- reverting
#
# B1.3 wrote the pre-edit snapshot so that "撤销" could exist, and then nothing read
# that snapshot back: `snapshot_version_id` has no consumer in the frontend, and the
# one screen that lists versions filters `format === 'md'`, so the JSON row never
# even reaches the UI. These tests cover the endpoint that finally reads it, plus the
# shape check that decides *which* rows may be written back — an "optimized"/"tailored"
# JSON version is AI-authored content in a different shape, and restoring it through a
# button labelled "undo" would put generated text into a candidate's CV.


def _apply_once(
    db,
    user,
    resume,
    proposed="三年后端开发经验，专注订单链路",
    block_id="self_evaluation",
    expected="三年后端开发经验",
    **kwargs,
):
    edit = {"block_id": block_id, "proposed_text": proposed}
    if expected is not None:
        edit["expected_original"] = expected
    return svc.apply_rewrite_suggestions(db, resume.id, [edit], user_id=user.id, **kwargs)


def test_revert_restores_the_text_the_rewrite_overwrote(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    before_version = resume_version_of(resume)

    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] != "三年后端开发经验"

    result = svc.revert_rewrite_suggestions(db_session, resume.id, applied["snapshot_version_id"], user_id=user.id)
    db_session.expire_all()

    assert result["changed"] is True
    assert result["restored_blocks"] == ["self_evaluation"]
    fresh = db_session.get(Resume, resume.id)
    assert fresh.parsed_json["self_evaluation"] == "三年后端开发经验"
    # Restoring also restores the version identity every score cache keys off, so the
    # candidate sees the same number they saw before the rewrite.
    assert result["resume_version"] == before_version


def test_revert_is_refused_when_the_candidate_reworked_a_block_afterwards(db_session, actor):
    """Same judgement as `expected_original`: anchors are positional, and a blind
    restore would eat the newer words the candidate wrote after applying."""
    user, _ = actor
    resume = _resume_row(db_session, user)
    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()

    resume = db_session.get(Resume, resume.id)
    resume.parsed_json = {**resume.parsed_json, "self_evaluation": "候选人应用之后自己又改过的那句"}
    db_session.add(resume)
    db_session.commit()

    result = svc.revert_rewrite_suggestions(db_session, resume.id, applied["snapshot_version_id"], user_id=user.id)
    db_session.expire_all()

    assert result["changed"] is False
    assert result["reverted"] is False
    assert result["stale_blocks"] == [
        {"block_id": "self_evaluation", "kind": "self_evaluation", "reason": "stale_block"}
    ]
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "候选人应用之后自己又改过的那句"
    # A refused revert must not leave the "撤销前" row behind either.
    assert db_session.query(ResumeVersion).filter(ResumeVersion.label == svc.REVERT_LABEL).count() == 0


def test_reverting_the_revert_restores_the_rewrite(db_session, actor):
    """The revert writes an inverse change_log, so it is its own inverse."""
    user, _ = actor
    resume = _resume_row(db_session, user)
    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()

    first = svc.revert_rewrite_suggestions(db_session, resume.id, applied["snapshot_version_id"], user_id=user.id)
    db_session.expire_all()
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "三年后端开发经验"

    second = svc.revert_rewrite_suggestions(db_session, resume.id, first["undo_version_id"], user_id=user.id)
    db_session.expire_all()

    assert second["changed"] is True
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "三年后端开发经验，专注订单链路"


def test_only_a_rewrite_snapshot_can_be_reverted(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()
    snapshot_id = applied["snapshot_version_id"]

    def _add(**kwargs):
        row = ResumeVersion(
            resume_id=resume.id,
            version_type=kwargs.pop("version_type", "optimized"),
            content=kwargs.pop("content", json.dumps({"skills": ["模型生成的内容"]}, ensure_ascii=False)),
            format=kwargs.pop("format", "json"),
            label=kwargs.pop("label", "AI 优化版数据"),
            change_log=kwargs.pop("change_log", None),
        )
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        return row

    # 生产 `format == "json"` 行的另两路，和一条 change_log 空的手动行，全部不能被撤销
    for row in [_add(), _add(version_type="tailored", label="定制版数据"), _add(version_type="manual", change_log=[])]:
        with pytest.raises(ValueError):
            svc.revert_rewrite_suggestions(db_session, resume.id, row.id, user_id=user.id)

    # 最险的一种：一条 optimized + json **且 change_log 非空**的行。今天没有生产者这样写
    # （`resume_export_service` 把 change_log 挂在 md 那行上），但它一旦存在，"只看 change_log"
    # 那种收窄的判据就会放行，而 content 是模型生成的结构化数据——撤销按钮会把 AI 写的东西
    # 当成"你原来的文字"塞回简历。挡住它的那一条是 `version_type == "manual"`。
    with pytest.raises(ValueError):
        svc.revert_rewrite_suggestions(
            db_session,
            resume.id,
            _add(
                change_log=[{"block_id": "self_evaluation", "before": "三年后端开发经验", "after": "模型写的句子"}]
            ).id,
            user_id=user.id,
        )

    # 一条 md 行也不行——它是给导出和对比用的另一份投影
    md_row = _add(version_type="manual", format="md", content="# markdown", change_log=applied["applied"])
    with pytest.raises(ValueError):
        svc.revert_rewrite_suggestions(db_session, resume.id, md_row.id, user_id=user.id)

    # 别的简历的快照 id 落在这份简历上查不到
    other_resume = _resume_row(db_session, actor[1])
    with pytest.raises(ValueError):
        svc.revert_rewrite_suggestions(db_session, other_resume.id, snapshot_id, user_id=actor[1].id)

    # 反过来，真快照确实能撤 —— 上面四条红不是因为函数根本跑不通
    assert svc.revert_rewrite_suggestions(db_session, resume.id, snapshot_id, user_id=user.id)["changed"] is True


def test_cross_user_revert_is_refused(db_session, actor):
    user, other = actor
    resume = _resume_row(db_session, user)
    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()

    with pytest.raises(ValueError):
        svc.revert_rewrite_suggestions(db_session, resume.id, applied["snapshot_version_id"], user_id=other.id)
    db_session.expire_all()
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "三年后端开发经验，专注订单链路"


def test_revert_moves_the_match_score_back_and_keeps_both_cache_rows(db_session, actor):
    from app.models.match_score import MatchScore

    user, _ = actor
    resume = _resume_row(db_session, user)
    job = _job_row(db_session, user)
    baseline = canonical_match_score(db_session, resume, job, user_id=user.id, persist=False)["score"]

    applied = _apply_once(
        db_session,
        user,
        resume,
        block_id="skills",
        expected=None,
        proposed="Python、FastAPI、MySQL",
        jd_id=job.id,
    )
    db_session.expire_all()
    assert applied["score"]["delta"] > 0

    result = svc.revert_rewrite_suggestions(db_session, resume.id, applied["snapshot_version_id"], user_id=user.id)

    assert result["score"]["before"] == applied["score"]["after"]
    assert result["score"]["after"]["score"] == baseline
    assert result["score"]["delta"] == -applied["score"]["delta"]
    # Nothing had to be invalidated: rows are keyed by the parsed_json hash, so both
    # versions keep their own score and the revert simply reads the older one again.
    assert db_session.query(MatchScore).filter(MatchScore.resume_id == resume.id).count() == 2


def test_revert_still_restores_the_text_when_the_target_job_is_gone(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    job = _job_row(db_session, user)
    applied = _apply_once(
        db_session, user, resume, block_id="skills", expected=None, proposed="Python、FastAPI、MySQL", jd_id=job.id
    )
    db_session.expire_all()

    db_session.delete(db_session.get(JobDescription, job.id))
    db_session.commit()

    result = svc.revert_rewrite_suggestions(db_session, resume.id, applied["snapshot_version_id"], user_id=user.id)
    db_session.expire_all()

    assert result["changed"] is True
    assert result["score"]["after"] is None
    assert result["score_note"] == "目标岗位已不可见，这次不显示匹配分变化"
    assert db_session.get(Resume, resume.id).parsed_json["skills"] == ["Python", "FastAPI"]


def test_the_revert_endpoint_persists_through_http_and_checks_its_argument(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()

    with TestClient(_resume_client(db_session, user)) as client:
        missing = client.post(f"/resume/{resume.id}/revert-rewrite", json={}).json()
        not_a_number = client.post(f"/resume/{resume.id}/revert-rewrite", json={"snapshot_version_id": "abc"}).json()
        bool_id = client.post(f"/resume/{resume.id}/revert-rewrite", json={"snapshot_version_id": True}).json()
        body = client.post(
            f"/resume/{resume.id}/revert-rewrite",
            json={"snapshot_version_id": applied["snapshot_version_id"]},
        ).json()

    assert missing["code"] != 0 and "snapshot_version_id" in missing["message"]
    assert not_a_number["code"] != 0
    # `int(True) == 1` would quietly restore whichever row happens to have id 1
    assert bool_id["code"] != 0
    assert body["code"] == 0
    assert body["data"]["changed"] is True
    db_session.expire_all()
    assert db_session.get(Resume, resume.id).parsed_json["self_evaluation"] == "三年后端开发经验"


def test_the_revert_endpoint_reports_a_stale_snapshot_without_an_error_code(db_session, actor):
    user, _ = actor
    resume = _resume_row(db_session, user)
    applied = _apply_once(db_session, user, resume)
    db_session.expire_all()

    resume = db_session.get(Resume, resume.id)
    resume.parsed_json = {**resume.parsed_json, "self_evaluation": "自己改过的一句"}
    db_session.add(resume)
    db_session.commit()

    with TestClient(_resume_client(db_session, user)) as client:
        body = client.post(
            f"/resume/{resume.id}/revert-rewrite",
            json={"snapshot_version_id": applied["snapshot_version_id"]},
        ).json()

    assert body["code"] == 0
    assert body["data"]["changed"] is False
    assert "没有撤销" in body["message"]


def test_the_revert_endpoint_is_registered():
    app = FastAPI()
    app.include_router(resume_router, prefix="/resume")
    paths = {route.path for route in app.routes}

    assert "/resume/{resume_id}/revert-rewrite" in paths
