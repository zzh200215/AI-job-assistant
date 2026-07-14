import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.knowledge import router as knowledge_router
from app.core.database import get_db
from app.services.embedding_service import reset_embedding_stats


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(knowledge_router, prefix="/knowledge")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client, *, username, email, db_session=None):
    if username == "admin":
        from app.core.security import hash_password
        from app.models.user import User

        admin = User(
            username=username,
            email=email,
            password=hash_password("StrongP@ssw0rd"),
            role="candidate",
        )
        db_session.add(admin)
        db_session.commit()
        response = client.post(
            "/auth/login",
            json={"account": username, "password": "StrongP@ssw0rd"},
        )
    else:
        response = client.post(
            "/auth/register",
            json={
                "username": username,
                "email": email,
                "password": "StrongP@ssw0rd",
            },
        )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_embedding_stats_api_requires_admin(client):
    headers = _register_and_login(client, username="normal_user", email="normal@example.com")

    response = client.get("/knowledge/admin/embedding-stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0
    assert body["message"] == "admin only"


def test_embedding_stats_api_returns_runtime_stats_for_admin(client, db_session):
    reset_embedding_stats()
    headers = _register_and_login(client, username="admin", email="admin@example.com", db_session=db_session)

    response = client.get("/knowledge/admin/embedding-stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert "total_calls" in body["data"]
    assert "cache_hit_rate" in body["data"]
    assert "provider_totals" in body["data"]
    assert "daily_trend" in body["data"]
