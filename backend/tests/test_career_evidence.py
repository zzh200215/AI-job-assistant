"""B2.3: a career direction must show the postings it was derived from.

`/career-path/recommend` used to receive only a resume summary and return
directions with invented `gap_skills`. Every number now comes from the job
library, and the model is confined to ranking directions that already exist.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import career_path_agent as agent_mod
from app.api.auth import get_current_user
from app.api.career_path import router as career_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.history import JobDescription, Resume
from app.models.user import User
from app.services.career_evidence import derive_directions, direction_key

RESUME_PARSED = {
    "name": "张三",
    "skills": ["Python", "Redis"],
    "years_exp": 4,
    "education": "本科",
    "current_title": "后端工程师",
    "work_experience": [],
    "project_experience": [],
}


@pytest.fixture
def user(db_session):
    row = User(
        username="ce_user", email="ce_user@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def other_user(db_session):
    row = User(
        username="ce_other", email="ce_other@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _job(db, owner, title, *, salary="", required=(), nice=(), location="上海", skill_tags=None):
    row = JobDescription(
        user_id=owner.id,
        title=title,
        company="示例公司",
        location=location,
        salary_range=salary,
        raw_text=title,
        is_active=1,
        skill_tags=skill_tags or [],
        parsed_json={"title": title, "required_skills": list(required), "nice_to_have": list(nice)},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _resume_row(db, owner):
    row = Resume(
        user_id=owner.id,
        name="方向验证简历",
        file_name="cd.pdf",
        file_path="uploads/cd.pdf",
        file_type="pdf",
        file_size=1024,
        parsed_json=dict(RESUME_PARSED),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------- grouping


@pytest.mark.parametrize(
    "title,expected",
    [
        ("高级前端开发工程师", "前端开发工程师"),
        ("前端 开发工程师", "前端开发工程师"),
        ("资深 Java 工程师", "java工程师"),
        ("Junior Backend Engineer", "backend engineer"),
        ("AI 算法工程师", "ai算法工程师"),
        ("AI算法工程师", "ai算法工程师"),
        ("产品经理", "产品经理"),
        ("研发总监", "研发总监"),
        ("", ""),
    ],
)
def test_grouping_ignores_seniority_not_direction(title, expected):
    assert direction_key(title) == expected


def test_role_nouns_are_not_stripped():
    """ "经理" is a modifier in "研发经理" but the whole role in "产品经理";
    stripping it would merge unrelated directions, so it never is."""
    assert direction_key("高级产品经理") == direction_key("产品经理")
    assert direction_key("产品经理") != direction_key("产品")


def test_two_seniority_variants_become_one_direction(db_session, user):
    _job(db_session, user, "后端开发工程师", required=["Python"], salary="20-30K")
    _job(db_session, user, "高级后端开发工程师", required=["Python", "MySQL"], salary="30-45K")
    _job(db_session, user, "前端开发工程师", required=["Vue"], salary="18-28K")

    directions, corpus = derive_directions(db_session, RESUME_PARSED, user)

    assert corpus["visible_jds"] == 3
    assert [len(d.key) > 0 for d in directions]
    assert directions[0].label == "后端开发工程师"
    assert directions[0].sample_count == 2
    assert corpus["directions_found"] == 2


def test_a_direction_lists_exactly_its_own_postings(db_session, user):
    a = _job(db_session, user, "后端开发工程师", required=["Python"], salary="20-30K")
    b = _job(db_session, user, "资深后端开发工程师", required=["Redis"], salary="25-35K")
    other = _job(db_session, user, "产品经理", required=["沟通"], salary="15-20K")

    directions, _ = derive_directions(db_session, RESUME_PARSED, user)

    by_key = {d.key: d for d in directions}
    assert by_key["后端开发工程师"].jd_ids == [a.id, b.id]
    assert by_key["产品经理"].jd_ids == [other.id]


def test_coverage_counts_the_union_of_requirements(db_session, user):
    _job(db_session, user, "后端开发工程师", required=["Python", "MySQL"], salary="20-30K")
    _job(db_session, user, "高级后端开发工程师", required=["Redis"], salary="30-40K")

    directions, _ = derive_directions(db_session, RESUME_PARSED, user)
    backend = next(d for d in directions if "后端" in d.key)

    # Candidate has Python + Redis; the direction asks for Python, MySQL, Redis.
    assert backend.required_total == 3
    assert backend.coverage == pytest.approx(2 / 3, abs=0.01)
    assert [row["skill"] for row in backend.gap_skills] == ["mysql"]


def test_salary_evidence_is_scoped_to_the_direction(db_session, user):
    _job(db_session, user, "后端开发工程师", salary="20-30K")
    _job(db_session, user, "高级后端开发工程师", salary="40-50K")
    _job(db_session, user, "产品经理", salary="100-120K")

    directions, _ = derive_directions(db_session, RESUME_PARSED, user)
    backend = next(d for d in directions if "后端" in d.key)

    assert backend.salary["has_data"] is True
    assert backend.salary["sample_size"] == 2
    assert backend.salary["p25"] == 25.0
    assert len(backend.salary["sample_jd_ids"]) == 2


def test_thin_or_salary_free_directions_are_flagged(db_session, user):
    _job(db_session, user, "唯一岗", required=["Go"])
    _job(db_session, user, "双岗工程师", salary="10-20K")
    _job(db_session, user, "高级双岗工程师", salary="20-30K")

    directions, _ = derive_directions(db_session, RESUME_PARSED, user)
    by_key = {d.key: d for d in directions}

    assert by_key["唯一岗"].degraded is True
    assert any("样本" in reason for reason in by_key["唯一岗"].degrade_reasons)
    assert by_key["唯一岗"].salary["has_data"] is False
    assert by_key["双岗工程师"].degraded is True, "two postings is still not a market"
    assert by_key["双岗工程师"].sample_count == 2


def test_private_postings_of_other_users_are_not_counted(db_session, user, other_user):
    _job(db_session, user, "后端开发工程师", required=["Python"])
    _job(db_session, other_user, "后端开发工程师", required=["Python"])

    directions, corpus = derive_directions(db_session, RESUME_PARSED, user)

    assert corpus["visible_jds"] == 1
    assert directions[0].sample_count == 1
    other_directions, other_corpus = derive_directions(db_session, RESUME_PARSED, other_user)
    assert other_corpus["visible_jds"] == 1
    assert other_directions[0].jd_ids != directions[0].jd_ids


def test_no_visible_postings_yields_no_directions(db_session, user):
    directions, corpus = derive_directions(db_session, RESUME_PARSED, user)

    assert directions == []
    assert corpus["visible_jds"] == 0


# ---------------------------------------------------------------- the model's gate


def _direction(key: str, coverage: float | None = 0.8) -> agent_mod.CareerDirection:
    from app.services.career_evidence import CareerDirection

    return CareerDirection(
        key=key,
        label=key,
        jd_ids=[1],
        sample_count=3,
        required_total=5,
        matched_skills=["python"],
        gap_skills=[{"skill": "mysql", "required_count": 2, "nice_count": 0, "priority": "高"}],
        coverage=coverage,
        salary={"has_data": True, "p50": 30.0, "sample_size": 3, "low_confidence": False, "sample_jd_ids": [1]},
        degraded=False,
        degrade_reasons=[],
    )


def test_invented_directions_are_refused():
    directions = [_direction("后端工程师")]
    payload = {
        "career_paths": [
            {"direction_key": "首席架构师", "category": "高度匹配", "reason": "凭空造出来的方向"},
            {"direction_key": "后端工程师", "category": "高度匹配", "reason": "覆盖度高"},
            {"direction_key": "后端工程师", "category": "可转型", "reason": "重复"},
        ]
    }

    accepted, rejected = agent_mod.validate_career_paths(directions, payload)

    assert [p["direction_key"] for p in accepted] == ["后端工程师"]
    assert [r["reason"] for r in rejected] == ["unknown_direction", "duplicate_direction"]


def test_an_invented_category_falls_back_to_the_rule():
    directions = [_direction("算法工程师", coverage=0.2)]

    accepted, _ = agent_mod.validate_career_paths(
        directions, {"career_paths": [{"direction_key": "算法工程师", "category": "百分百匹配", "reason": "x"}]}
    )

    assert accepted[0]["category"] == "可转型"


def test_malformed_payload_is_reported_not_crashed():
    assert agent_mod.validate_career_paths([_direction("a")], {"nope": 1})[1] == [
        {"direction_key": None, "reason": "malformed_response"}
    ]


def test_rule_reason_states_the_evidence_and_the_weakness():
    thin = _direction("数据工程师")
    thin.coverage = None
    thin.degraded = True
    thin.degrade_reasons = ["仅 1 条岗位样本"]

    assert "未列出可核对的硬性要求" in agent_mod.rule_reason(thin)
    assert "仅 1 条岗位样本" in agent_mod.rule_reason(thin)
    assert "约 80%" in agent_mod.rule_reason(_direction("后端工程师"))


def test_mocked_model_output_is_replaced_by_rule_reason(db_session, user, monkeypatch):
    directions = [_direction("后端工程师"), _direction("算法工程师", coverage=0.3)]
    monkeypatch.setattr(
        agent_mod,
        "chat_json",
        lambda prompt: {
            "career_paths": [{"direction_key": "后端工程师", "category": "高度匹配", "reason": "模型编的理由"}],
            "summary": "模型总结",
        },
    )
    monkeypatch.setattr(agent_mod, "get_llm_provenance", lambda: {"source": "mock"})

    result = agent_mod.CareerPathAgent().recommend(RESUME_PARSED, directions)

    assert result["reason_source"] == "rules"
    assert result["career_paths"][0]["reason"] == agent_mod.rule_reason(directions[0])
    assert "模型" not in result["summary"]


def test_real_model_reasons_are_kept(db_session, user, monkeypatch):
    directions = [_direction("后端工程师")]
    monkeypatch.setattr(
        agent_mod,
        "chat_json",
        lambda prompt: {
            "career_paths": [
                {"direction_key": "后端工程师", "category": "高度匹配", "reason": "已覆盖核心栈", "seniority": "高级"}
            ],
            "summary": "先投覆盖度高的",
        },
    )
    monkeypatch.setattr(agent_mod, "get_llm_provenance", lambda: {"source": "real"})

    result = agent_mod.CareerPathAgent().recommend(RESUME_PARSED, directions)

    assert result["reason_source"] == "model"
    assert result["career_paths"][0]["reason"] == "已覆盖核心栈"
    assert result["career_paths"][0]["seniority"] == "高级"
    assert result["summary"] == "先投覆盖度高的"


def test_no_directions_costs_no_model_call(monkeypatch):
    calls = []
    monkeypatch.setattr(agent_mod, "chat_json", lambda prompt: calls.append(prompt) or {})

    result = agent_mod.CareerPathAgent().recommend(RESUME_PARSED, [])

    assert calls == []
    assert result["career_paths"] == []


# ---------------------------------------------------------------- endpoint


@pytest.fixture
def client(db_session, user):
    app = FastAPI()
    app.include_router(career_router, prefix="/career-path")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as test_client:
        yield test_client


def test_endpoint_returns_evidence_per_direction(client, db_session, user, monkeypatch):
    _job(db_session, user, "后端开发工程师", required=["Python", "MySQL"], salary="20-30K")
    _job(db_session, user, "高级后端开发工程师", required=["Python"], salary="30-40K")
    resume = _resume_row(db_session, user)
    monkeypatch.setattr(agent_mod, "get_llm_provenance", lambda: {"source": "real"})
    monkeypatch.setattr(
        agent_mod,
        "chat_json",
        lambda prompt: {
            "career_paths": [{"direction_key": "后端开发工程师", "category": "高度匹配", "reason": "栈重合"}],
            "summary": "先投后端",
        },
    )

    body = client.post("/career-path/recommend", params={"resume_id": resume.id}).json()

    assert body["code"] == 0
    path = body["data"]["career_paths"][0]
    assert path["direction_key"] == "后端开发工程师"
    assert path["reason"] == "栈重合"
    assert path["sample_count"] == 2
    assert len(path["jd_ids"]) == 2
    assert path["salary"]["p50"] == 25.0
    assert path["coverage"] is not None


def test_endpoint_still_returns_directions_when_the_model_gives_nothing(client, db_session, user, monkeypatch):
    _job(db_session, user, "数据工程师", required=["Python"], salary="25-35K")
    resume = _resume_row(db_session, user)
    monkeypatch.setattr(agent_mod, "chat_json", lambda prompt: {})

    data = client.post("/career-path/recommend", params={"resume_id": resume.id}).json()["data"]

    assert data["reason_source"] == "rules"
    assert data["career_paths"][0]["label"] == "数据工程师"
    assert data["career_paths"][0]["reason_source"] == "rules"


def test_endpoint_reports_an_empty_library_without_inventing_anything(client, db_session, user):
    resume = _resume_row(db_session, user)

    data = client.post("/career-path/recommend", params={"resume_id": resume.id}).json()

    assert data["code"] == 0
    assert data["data"]["career_paths"] == []
    assert "没有可统计的岗位" in data["message"]
    assert data["data"]["corpus"]["visible_jds"] == 0


def test_endpoint_still_rejects_another_users_resume(client, db_session, other_user):
    resume = _resume_row(db_session, other_user)

    body = client.post("/career-path/recommend", params={"resume_id": resume.id}).json()

    assert body["code"] != 0
