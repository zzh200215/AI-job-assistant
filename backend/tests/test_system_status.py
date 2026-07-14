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
    assert data["capabilities"]["social_login"] is False
    assert data["capabilities"]["password_reset"] is True
    assert isinstance(data["capabilities"]["ocr_resume_parse"], bool)


def test_system_status_reports_configured_feishu_sso(client, monkeypatch):
    monkeypatch.setattr(system.settings, "FEISHU_APP_ID", "cli_test")
    monkeypatch.setattr(system.settings, "FEISHU_APP_SECRET", "secret")
    monkeypatch.setattr(system.settings, "FEISHU_REDIRECT_URI", "https://example.test/callback")
    register_response = register_user(client)
    token = register_response.json()["data"]["access_token"]

    response = client.get("/system/status", headers={"Authorization": f"Bearer {token}"})

    capabilities = response.json()["data"]["capabilities"]
    assert capabilities["social_login"] is True
    assert capabilities["feishu_sso"] is True


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
