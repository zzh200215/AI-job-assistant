from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agent import router as agent_router
from app.api.auth import router as auth_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.agent import AgentStepLog, AgentTask
from app.models.user import User
from app.services.orchestration_runner import mark_stale_running_tasks_failed
from app.utils.time_helper import utc_now


@pytest.fixture
def agent_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(agent_router, prefix="/agent")

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


def _create_task(db_session, *, user_id: int, resume_id: int = 1, jd_id: int = 1, status: str = "running") -> AgentTask:
    now = utc_now()
    task = AgentTask(
        user_id=user_id,
        resume_id=resume_id,
        jd_id=jd_id,
        status=status,
        start_time=now - timedelta(seconds=5),
        end_time=now if status == "completed" else None,
        plan=[{"step": "intent"}, {"step": "match"}, {"step": "summary"}],
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _create_step(db_session, *, task_id: int, step_index: int, name: str, status: str) -> AgentStepLog:
    now = utc_now()
    step = AgentStepLog(
        task_id=task_id,
        step_name=name,
        step_index=step_index,
        status=status,
        started_at=now - timedelta(seconds=max(3 - step_index, 0)),
        completed_at=now if status in {"completed", "failed"} else None,
        duration_ms=800 if status in {"completed", "failed"} else None,
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(step)
    return step


def test_task_list_returns_only_current_user_tasks_with_progress(agent_client, db_session):
    owner = _create_user(db_session, "task_owner", "task_owner@example.com")
    other = _create_user(db_session, "task_other", "task_other@example.com")

    owner_task = _create_task(db_session, user_id=owner.id, status="running")
    _create_step(db_session, task_id=owner_task.id, step_index=0, name="intent_analysis", status="completed")
    _create_step(db_session, task_id=owner_task.id, step_index=1, name="matching_analysis", status="running")

    other_task = _create_task(db_session, user_id=other.id, status="completed")
    _create_step(db_session, task_id=other_task.id, step_index=0, name="intent_analysis", status="completed")

    response = agent_client.get("/agent/tasks", headers=_auth_headers(owner))

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] == 1
    assert len(body["items"]) == 1
    task = body["items"][0]
    assert task["id"] == owner_task.id
    assert task["progress"]["step_counts"]["completed"] == 1
    assert task["progress"]["step_counts"]["running"] == 1
    assert task["progress"]["current_step"]["name"] == "match_analysis"
    assert task["progress"]["progress_percent"] > 0


def test_task_summary_returns_status_counts_and_recent_tasks(agent_client, db_session):
    owner = _create_user(db_session, "summary_owner", "summary_owner@example.com")

    running_task = _create_task(db_session, user_id=owner.id, status="running")
    completed_task = _create_task(db_session, user_id=owner.id, status="completed")
    _create_step(db_session, task_id=running_task.id, step_index=0, name="intent_analysis", status="running")
    _create_step(db_session, task_id=completed_task.id, step_index=0, name="intent_analysis", status="completed")

    response = agent_client.get("/agent/tasks/summary", headers=_auth_headers(owner))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["counts"]["running"] == 1
    assert data["counts"]["completed"] == 1
    assert data["total"] == 2
    assert len(data["recent"]) == 2


def test_single_task_endpoint_includes_progress_block(agent_client, db_session):
    owner = _create_user(db_session, "detail_owner", "detail_owner@example.com")
    task = _create_task(db_session, user_id=owner.id, status="completed")
    _create_step(db_session, task_id=task.id, step_index=0, name="intent_analysis", status="completed")
    _create_step(db_session, task_id=task.id, step_index=1, name="summary_report", status="completed")

    response = agent_client.get(f"/agent/task/{task.id}", headers=_auth_headers(owner))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == task.id
    assert data["progress"]["progress_percent"] == 100
    assert data["progress"]["duration_ms"] is not None
    assert data["progress"]["current_step"]["status"] == "completed"


def test_cancel_task_endpoint_marks_task_cancelled(agent_client, db_session):
    owner = _create_user(db_session, "cancel_owner", "cancel_owner@example.com")
    task = _create_task(db_session, user_id=owner.id, status="running")

    response = agent_client.post(f"/agent/task/{task.id}/cancel", headers=_auth_headers(owner))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "cancelled"
    assert data["error_msg"] == "Cancelled by user"


def test_retry_task_endpoint_creates_new_retry_task(agent_client, db_session, monkeypatch):
    owner = _create_user(db_session, "retry_owner", "retry_owner@example.com")
    original = _create_task(db_session, user_id=owner.id, status="failed")
    original.strategy_name = "linear"
    original.error_msg = "boom"
    db_session.add(original)
    db_session.commit()

    captured = {}

    def fake_start_strategy_thread(strategy_name, task_id, resume_id, jd_id, user_id=None):
        captured["strategy_name"] = strategy_name
        captured["task_id"] = task_id
        captured["resume_id"] = resume_id
        captured["jd_id"] = jd_id
        captured["user_id"] = user_id

    monkeypatch.setattr(
        "app.services.orchestration_runner.start_strategy_thread",
        fake_start_strategy_thread,
    )

    response = agent_client.post(f"/agent/task/{original.id}/retry", headers=_auth_headers(owner))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] != original.id
    assert data["retry_of_task_id"] == original.id
    assert data["strategy_name"] == "linear"
    assert captured["strategy_name"] == "linear"
    assert captured["user_id"] == owner.id


def test_mark_stale_running_tasks_failed_only_updates_old_running_tasks(db_session):
    owner = _create_user(db_session, "stale_owner", "stale_owner@example.com")
    stale = _create_task(db_session, user_id=owner.id, status="running")
    fresh = _create_task(db_session, user_id=owner.id, status="running")
    done = _create_task(db_session, user_id=owner.id, status="completed")
    stale.start_time = utc_now() - timedelta(minutes=45)
    fresh.start_time = utc_now() - timedelta(minutes=5)
    done.start_time = utc_now() - timedelta(minutes=45)
    db_session.add_all([stale, fresh, done])
    db_session.commit()

    count = mark_stale_running_tasks_failed(older_than_minutes=30, db=db_session)
    db_session.refresh(stale)
    db_session.refresh(fresh)
    db_session.refresh(done)

    assert count == 1
    assert stale.status == "failed"
    assert stale.end_time is not None
    assert fresh.status == "running"
    assert done.status == "completed"


def test_task_list_includes_usage_from_step_outputs(agent_client, db_session):
    owner = _create_user(db_session, "usage_owner", "usage_owner@example.com")
    task = _create_task(db_session, user_id=owner.id, status="completed")
    step = AgentStepLog(
        task_id=task.id,
        step_name="matching_analysis",
        step_index=0,
        status="completed",
        output_data={"_usage": {"total_tokens": 1200, "cost_cents": 3.25}},
        completed_at=utc_now(),
    )
    db_session.add(step)
    db_session.commit()

    response = agent_client.get("/agent/tasks", headers=_auth_headers(owner))

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["usage"]["tokens_used"] == 1200
    assert item["usage"]["cost_cents"] == 3.25
