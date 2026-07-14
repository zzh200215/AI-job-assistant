from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.prompt_trace import router as prompt_trace_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.prompt_trace import PromptTrace
from app.models.user import User


@pytest.fixture
def prompt_trace_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(prompt_trace_router, prefix="/prompt-traces")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _create_trace(
    db_session,
    *,
    user_id: int,
    source: str = "match_service.analyze",
    prompt_version: str = "v1",
    status: str = "success",
    duration_ms: int = 1200,
    total_tokens: int = 900,
    cost_cents: float = 1.2,
    task_id: int | None = None,
    analysis_record_id: int | None = None,
    created_at: datetime | None = None,
) -> PromptTrace:
    trace = PromptTrace(
        request_id=f"req-{user_id}-{source}-{prompt_version}-{status}-{duration_ms}",
        source=source,
        prompt_version=prompt_version,
        provider="openai",
        model="gpt-4.1-mini",
        status=status,
        cache_hit=0,
        duration_ms=duration_ms,
        prompt_chars=2400,
        prompt_hash=f"hash-{prompt_version}",
        prompt_text=f"prompt for {prompt_version}",
        response_text=f"response for {prompt_version}",
        response_json={"score": 82},
        prompt_family="match",
        prompt_name="match-agent",
        trace_context={"source": source, "request_id": f"req-{user_id}"},
        prompt_metadata={"prompt_version": prompt_version, "prompt_family": "match", "prompt_name": "match-agent"},
        total_tokens=total_tokens,
        prompt_tokens=500,
        completion_tokens=400,
        cost_cents=cost_cents,
        task_id=task_id,
        analysis_record_id=analysis_record_id,
        user_id=user_id,
        created_at=created_at or datetime(2026, 6, 25, 10, 0, 0),
    )
    db_session.add(trace)
    db_session.commit()
    db_session.refresh(trace)
    return trace


def test_prompt_trace_list_and_summary_only_show_current_user(prompt_trace_client, db_session):
    owner = _create_user(db_session, "trace_owner", "trace_owner@example.com")
    other = _create_user(db_session, "trace_other", "trace_other@example.com")

    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="v1",
        status="success",
        duration_ms=1000,
        total_tokens=800,
        cost_cents=1.1,
        created_at=datetime(2026, 6, 24, 9, 0, 0),
    )
    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="v2",
        status="failed",
        duration_ms=1500,
        total_tokens=1000,
        cost_cents=1.4,
        created_at=datetime(2026, 6, 25, 9, 0, 0),
    )
    _create_trace(
        db_session,
        user_id=other.id,
        source="resume_service.parse",
        prompt_version="v9",
        status="success",
    )

    summary = prompt_trace_client.get("/prompt-traces/summary", headers=_auth_headers(owner))
    assert summary.status_code == 200
    body = summary.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 2
    assert body["data"]["success_count"] == 1
    assert body["data"]["failed_count"] == 1
    assert body["data"]["sources"] == ["match_service.analyze"]
    assert {item["prompt_version"] for item in body["data"]["version_groups"]} == {"v1", "v2"}
    assert body["data"]["versions"] == ["v1", "v2"]

    listing = prompt_trace_client.get("/prompt-traces/list", headers=_auth_headers(owner))
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["code"] == 0
    assert listing_body["data"]["total"] == 2
    assert len(listing_body["data"]["items"]) == 2
    assert {item["prompt_version"] for item in listing_body["data"]["items"]} == {"v1", "v2"}


def test_prompt_trace_detail_blocks_other_users(prompt_trace_client, db_session):
    owner = _create_user(db_session, "trace_detail_owner", "trace_detail_owner@example.com")
    outsider = _create_user(db_session, "trace_detail_outsider", "trace_detail_outsider@example.com")
    trace = _create_trace(db_session, user_id=owner.id, prompt_version="v3")

    denied = prompt_trace_client.get(f"/prompt-traces/{trace.id}", headers=_auth_headers(outsider))
    assert denied.status_code == 200
    assert denied.json()["code"] != 0

    allowed = prompt_trace_client.get(f"/prompt-traces/{trace.id}", headers=_auth_headers(owner))
    assert allowed.status_code == 200
    assert allowed.json()["code"] == 0
    assert allowed.json()["data"]["prompt_version"] == "v3"
    assert allowed.json()["data"]["prompt_text"] == "prompt for v3"


def test_prompt_trace_feedback_update(prompt_trace_client, db_session):
    owner = _create_user(db_session, "trace_feedback_owner", "trace_feedback_owner@example.com")
    trace = _create_trace(db_session, user_id=owner.id, prompt_version="v4")

    response = prompt_trace_client.post(
        f"/prompt-traces/{trace.id}/feedback",
        json={
            "feedback_label": "accepted",
            "feedback_note": "输出结构稳定",
            "feedback_score": 0.9,
        },
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["feedback_label"] == "accepted"
    assert body["data"]["feedback_score"] == 0.9


def test_prompt_trace_compare_returns_version_metrics(prompt_trace_client, db_session):
    owner = _create_user(db_session, "trace_compare_owner", "trace_compare_owner@example.com")

    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="v1",
        status="success",
        duration_ms=1100,
        total_tokens=850,
        cost_cents=1.0,
    )
    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="v1",
        status="success",
        duration_ms=1000,
        total_tokens=900,
        cost_cents=1.1,
        created_at=datetime(2026, 6, 25, 11, 0, 0),
    )
    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="v2",
        status="success",
        duration_ms=800,
        total_tokens=700,
        cost_cents=0.9,
        created_at=datetime(2026, 6, 25, 12, 0, 0),
    )
    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="v2",
        status="failed",
        duration_ms=950,
        total_tokens=760,
        cost_cents=0.95,
        created_at=datetime(2026, 6, 25, 13, 0, 0),
    )

    response = prompt_trace_client.get(
        "/prompt-traces/compare",
        params={"source": "match_service.analyze", "version_a": "v1", "version_b": "v2"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["version_a"]["metrics"]["total"] == 2
    assert body["data"]["version_b"]["metrics"]["total"] == 2
    assert body["data"]["version_a"]["metrics"]["success_rate"] == 1.0
    assert body["data"]["version_b"]["metrics"]["success_rate"] == 0.5
    assert body["data"]["delta"]["avg_duration_ms"] == -175.0
    assert len(body["data"]["version_a"]["recent_samples"]) == 2
    assert len(body["data"]["version_b"]["recent_samples"]) == 2


def test_prompt_trace_summary_and_list_support_task_filters(prompt_trace_client, db_session):
    owner = _create_user(db_session, "trace_scope_owner", "trace_scope_owner@example.com")

    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="task-v1",
        task_id=101,
        analysis_record_id=501,
    )
    _create_trace(
        db_session,
        user_id=owner.id,
        source="match_service.analyze",
        prompt_version="task-v2",
        task_id=102,
        analysis_record_id=502,
    )

    summary = prompt_trace_client.get(
        "/prompt-traces/summary",
        params={"task_id": 101},
        headers=_auth_headers(owner),
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["code"] == 0
    assert summary_body["data"]["total"] == 1
    assert summary_body["data"]["versions"] == ["task-v1"]

    listing = prompt_trace_client.get(
        "/prompt-traces/list",
        params={"analysis_record_id": 502},
        headers=_auth_headers(owner),
    )
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["code"] == 0
    assert listing_body["data"]["total"] == 1
    assert listing_body["data"]["items"][0]["prompt_version"] == "task-v2"
