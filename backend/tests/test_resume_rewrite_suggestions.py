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

from app.api.auth import get_current_user
from app.api.resume import router as resume_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.user import User
from app.services import resume_rewrite_service as svc
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
    monkeypatch.setattr(svc, "chat_json", lambda prompt: calls.append(prompt) or {})

    result = svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    assert calls == []
    assert result["suggestions"] == []
    assert "没有可供改写的文本块" in result["note"]


def test_suggestions_never_touch_the_stored_resume(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user)
    before = json.dumps(resume.parsed_json, ensure_ascii=False, sort_keys=True)
    monkeypatch.setattr(
        svc, "chat_json", lambda prompt: {"suggestions": [_suggestion(proposed="三年后端开发经验，专注高并发订单链路")]}
    )

    result = svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    assert len(result["suggestions"]) == 1
    db_session.expire_all()
    assert json.dumps(db_session.get(Resume, resume.id).parsed_json, ensure_ascii=False, sort_keys=True) == before


def test_the_prompt_carries_anchors_inside_a_data_boundary(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user)
    prompts = []
    monkeypatch.setattr(svc, "chat_json", lambda prompt: prompts.append(prompt) or {"suggestions": []})

    svc.build_rewrite_suggestions(db_session, resume.id, user_id=user.id)

    prompt = prompts[0]
    assert "work[0].desc" in prompt
    assert "<resume_blocks" in prompt  # candidate text is data, never instructions
    assert "prompt-render-v1" in prompt


def test_cross_user_resume_and_missing_job_are_refused(db_session, actor, monkeypatch):
    user, other = actor
    resume = _resume_row(db_session, user)
    job = _job_row(db_session, other)
    monkeypatch.setattr(svc, "chat_json", lambda prompt: {"suggestions": []})

    with pytest.raises(ValueError):
        svc.build_rewrite_suggestions(db_session, resume.id, user_id=other.id)

    with pytest.raises(ValueError):
        svc.build_rewrite_suggestions(db_session, resume.id, jd_id=999999, user_id=user.id)

    # A job owned by someone else is not a valid rewrite target either.
    with pytest.raises(ValueError):
        svc.build_rewrite_suggestions(db_session, resume.id, jd_id=job.id, user_id=user.id)


# ---------------------------------------------------------------- wiring


def test_the_endpoint_is_registered():
    app = FastAPI()
    app.include_router(resume_router, prefix="/resume")
    paths = {route.path for route in app.routes}

    assert "/resume/{resume_id}/rewrite-suggestions" in paths


def test_the_endpoint_reports_rejected_anchors_to_the_client(db_session, actor, monkeypatch):
    user, _ = actor
    resume = _resume_row(db_session, user)
    monkeypatch.setattr(
        svc,
        "chat_json",
        lambda prompt: {
            "suggestions": [
                _suggestion(proposed="三年后端开发经验，主导过订单链路重构"),
                _suggestion(block_id="work[3].desc", original="不存在"),
            ]
        },
    )

    with TestClient(_resume_client(db_session, user)) as client:
        body = client.post(f"/resume/{resume.id}/rewrite-suggestions", json={}).json()

    assert body["code"] == 0
    assert len(body["data"]["suggestions"]) == 1
    assert body["data"]["rejected"][0]["reason"] == "unknown_block"


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
