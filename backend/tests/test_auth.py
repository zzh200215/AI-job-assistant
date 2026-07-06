# -*- coding: utf-8 -*-
"""Authentication API tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.auth import router as auth_router
from app.core.database import get_db


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def register_user(client, **overrides):
    payload = {
        "username": "test_user",
        "email": "test@example.com",
        "password": "abc12345",
        "role": "candidate",
    }
    payload.update(overrides)
    return client.post("/auth/register", json=payload)


class TestAuthApi:
    def test_register_success_normalizes_input(self, client):
        response = register_user(
            client,
            username="  Test_User  ",
            email="  TEST@Example.com  ",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["user"]["username"] == "Test_User"
        assert body["data"]["user"]["email"] == "test@example.com"
        assert body["data"]["user"]["role"] == "candidate"
        assert body["data"]["access_token"]

    def test_register_rejects_public_recruiter_role(self, client):
        response = register_user(
            client,
            username="recruiter_user",
            email="recruiter@example.com",
            role="recruiter",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] != 0
        assert "求职者" in body["message"]

    def test_register_rejects_duplicate_email_case_insensitive(self, client):
        first = register_user(client, email="first@example.com")
        second = register_user(
            client,
            username="another_user",
            email="FIRST@example.com",
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["code"] != 0
        assert "邮箱" in second.json()["message"]

    def test_register_rejects_weak_password(self, client):
        response = register_user(client, password="weakpass")

        assert response.status_code == 422

    def test_login_supports_username(self, client):
        register_user(client, username="login_user", email="login@example.com")
        response = client.post(
            "/auth/login",
            json={"account": "LOGIN_USER", "password": "abc12345"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["user"]["username"] == "login_user"
        assert body["data"]["user"]["role"] == "candidate"

    def test_login_accepts_legacy_email_field(self, client):
        register_user(client)
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "abc12345"},
        )

        assert response.status_code == 200
        assert response.json()["code"] == 0

    def test_reset_password_updates_credentials(self, client):
        register_user(client, username="reset_user", email="reset@example.com")

        reset_response = client.post(
            "/auth/reset-password",
            json={
                "account": "reset_user",
                "email": "reset@example.com",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
        )

        assert reset_response.status_code == 200
        assert reset_response.json()["code"] == 0

        old_login = client.post(
            "/auth/login",
            json={"account": "reset_user", "password": "abc12345"},
        )
        assert old_login.status_code == 200
        assert old_login.json()["code"] != 0

        new_login = client.post(
            "/auth/login",
            json={"account": "reset@example.com", "password": "newpass123"},
        )
        assert new_login.status_code == 200
        assert new_login.json()["code"] == 0

    def test_reset_password_rejects_email_mismatch(self, client):
        register_user(client, username="mismatch_user", email="mismatch@example.com")

        response = client.post(
            "/auth/reset-password",
            json={
                "account": "mismatch_user",
                "email": "wrong@example.com",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
        )

        assert response.status_code == 200
        assert response.json()["code"] != 0

    def test_get_me_requires_valid_token(self, client):
        register_response = register_user(client, username="me_user", email="me@example.com")
        token = register_response.json()["data"]["access_token"]

        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["email"] == "me@example.com"
        assert body["data"]["role"] == "candidate"
        assert body["data"]["is_admin"] is False

    def test_register_rejects_reserved_admin_username(self, client):
        response = register_user(client, username="admin", email="admin@example.com")

        assert response.status_code == 200
        assert response.json()["code"] != 0

    def test_get_me_returns_is_admin_flag_for_seeded_admin(self, client, db_session):
        from app.core.security import hash_password
        from app.models.user import User

        admin = User(
            username="admin",
            email="real_admin@example.com",
            password=hash_password("abc12345"),
            role="candidate",
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)

        login = client.post(
            "/auth/login",
            json={"account": "admin", "password": "abc12345"},
        )

        assert login.status_code == 200
        body = login.json()
        assert body["code"] == 0
        assert body["data"]["user"]["is_admin"] is True

    def test_get_me_rejects_invalid_token(self, client):
        response = client.get("/auth/me", headers={"Authorization": "Bearer invalid"})

        assert response.status_code == 401
