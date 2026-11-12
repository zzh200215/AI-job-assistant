"""System status API tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import system
from app.api.auth import router as auth_router
from app.api.system import router as system_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.user import User


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(system_router, prefix="/system")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def register_user(client):
    return client.post(
        "/auth/register",
        json={
            "username": "status_user",
            "email": "status@example.com",
            "password": "StrongP@ssw0rd",
        },
    )


def create_user(db_session, *, username: str, email: str, role: str = "candidate") -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_system_status_requires_auth(client):
    response = client.get("/system/status")

    assert response.status_code == 401


def test_system_status_returns_runtime_flags(client):
    register_response = register_user(client)
    token = register_response.json()["data"]["access_token"]

    response = client.get("/system/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert "llm_provider" in data
    assert "embedding_provider" in data
    assert "reranker_provider" in data
    assert "demo_mode" in data
    assert "model_runtime" in data
    assert "ready" in data["model_runtime"]
    assert "configured" in data["model_runtime"]["llm"]
    assert "configured" in data["model_runtime"]["embedding"]
    assert data["capabilities"]["password_reset"] is True
    # 状态页不许报"有某种登录方式"而树里没有对应端点：`social_login` / `feishu_sso` 那两个键
    # 读的是三个 FEISHU_* 设置，而 SSO 路由早在 D134 就随企业侧出树了——环境变量配上也只会
    # 让管理员看到一句假话。键与设置一起撤，这里钉住"不再出现"。
    assert "social_login" not in data["capabilities"]


# ===== 候选人侧的两条运行时提示（演示数据 / AI 降级）=====
# 这两条是"把 A 阶段的诚实性工作搬到候选人屏幕上"的唯一出口，所以判据钉在"读得到"上：
# 降级信号原先只活在管理员 PromptTrace 页面里，候选人屏上一片干净。


def _seed_trace(db_session, *, degraded: int, minutes_ago: int, user: User) -> None:
    from datetime import timedelta

    from app.models.prompt_trace import PromptTrace
    from app.utils.time_helper import utc_now_naive

    db_session.add(
        PromptTrace(
            provider="openai",
            model="deepseek-v4-flash",
            status="success",
            degraded=degraded,
            created_at=utc_now_naive() - timedelta(minutes=minutes_ago),
            user_id=user.id,
        )
    )
    db_session.commit()


def test_status_reports_no_degradation_when_table_is_empty(client, db_session):
    user = create_user(db_session, username="deg_a", email="deg_a@example.com")

    data = client.get("/system/status", headers=auth_headers(user)).json()["data"]

    assert data["runtime_notes"]["ai_degraded_recent"] is False
    assert data["runtime_notes"]["ai_degraded_window_minutes"] == 30


def test_status_flags_a_recent_degraded_call(client, db_session):
    user = create_user(db_session, username="deg_b", email="deg_b@example.com")
    _seed_trace(db_session, degraded=1, minutes_ago=5, user=user)

    data = client.get("/system/status", headers=auth_headers(user)).json()["data"]

    assert data["runtime_notes"]["ai_degraded_recent"] is True


def test_status_ignores_degradation_older_than_the_window(client, db_session):
    """一次历史降级不该让横幅永久挂着——窗口是 30 分钟，所以 2 小时前那次不算"现在"。"""
    user = create_user(db_session, username="deg_c", email="deg_c@example.com")
    _seed_trace(db_session, degraded=1, minutes_ago=120, user=user)

    data = client.get("/system/status", headers=auth_headers(user)).json()["data"]

    assert data["runtime_notes"]["ai_degraded_recent"] is False
    assert "feishu_sso" not in data["capabilities"]
    assert isinstance(data["capabilities"]["ocr_resume_parse"], bool)


def test_system_status_exposes_ocr_capability(client, monkeypatch):
    monkeypatch.setattr(system, "is_ocr_available", lambda: True)
    register_response = register_user(client)
    token = register_response.json()["data"]["access_token"]

    response = client.get("/system/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["capabilities"]["ocr_resume_parse"] is True


def test_system_overview_rejects_candidate_role(client):
    register_response = register_user(client)
    token = register_response.json()["data"]["access_token"]

    response = client.get("/system/overview", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["code"] == -6
    assert body["detail"]["message"] == "仅管理员可查看系统概览"


def test_system_overview_returns_counts_for_admin(client, db_session):
    admin = create_user(
        db_session,
        username="status_admin",
        email="status_admin@example.com",
        role="admin",
    )

    response = client.get("/system/overview", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert "users" in data
    assert "resumes" in data
    assert "jds" in data
    assert "analysis_records" in data
    assert "runtime_metrics" in data
    assert "embedding_metrics" in data
    assert "current" in data["embedding_metrics"]
    assert "daily" in data["embedding_metrics"]


def test_model_probe_rejects_candidate_role(client):
    register_response = register_user(client)
    token = register_response.json()["data"]["access_token"]

    response = client.post("/system/model-probe", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_model_probe_returns_minimal_provider_checks(client, db_session, monkeypatch):
    admin = create_user(
        db_session,
        username="probe_admin",
        email="probe_admin@example.com",
        role="admin",
    )
    monkeypatch.setattr(
        system,
        "_model_runtime_status",
        lambda: {"ready": True, "live_ready": True, "llm": {"mode": "live"}, "embedding": {"mode": "live"}},
    )
    monkeypatch.setattr(system, "_probe_llm", lambda: {"ok": True, "latency_ms": 12})
    monkeypatch.setattr(system, "_probe_embedding", lambda: {"ok": True, "latency_ms": 8, "dimension": 1024})

    response = client.post("/system/model-probe", headers=auth_headers(admin))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["runtime"]["live_ready"] is True
    assert data["checks"]["llm"]["ok"] is True
    assert data["checks"]["embedding"]["dimension"] == 1024
