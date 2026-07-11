# -*- coding: utf-8 -*-
"""Admin role and authorization tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.system import router as system_router
from app.core.database import get_db
from app.core.security import create_access_token


def _client(db_session, *routers):
    app = FastAPI()
    for router, prefix in routers:
        app.include_router(router, prefix=prefix)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(db_session):
    yield from _client(db_session, (auth_router, "/auth"))


@pytest.fixture
def system_client(db_session):
    yield from _client(db_session, (system_router, "/system"))


class TestAdminAuth:
    def test_public_register_cannot_create_admin(self, auth_client):
        response = auth_client.post(
            "/auth/register",
            json={
                "username": "hacker",
                "email": "hacker@example.com",
                "password": "StrongP@ssw0rd",
                "role": "admin",
            },
        )
        assert response.status_code == 422

    def test_normal_user_cannot_access_admin_users(self, auth_client, normal_user):
        token = create_access_token({"sub": str(normal_user.id)})
        response = auth_client.get(
            "/auth/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_admin_can_list_users(self, auth_client, admin_user):
        token = create_access_token({"sub": str(admin_user.id)})
        response = auth_client.get(
            "/auth/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["total"] >= 1
        assert any(u["username"] == admin_user.username for u in body["data"]["items"])

    def test_admin_user_info_flags_is_admin(self, auth_client, admin_user):
        response = auth_client.post(
            "/auth/login",
            json={"account": admin_user.username, "password": "AdminPass123!"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["user"]["role"] == "admin"
        assert body["data"]["user"]["is_admin"] is True

    def test_normal_user_cannot_view_system_overview(self, system_client, normal_user):
        token = create_access_token({"sub": str(normal_user.id)})
        response = system_client.get(
            "/system/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_admin_can_view_system_overview(self, system_client, admin_user):
        token = create_access_token({"sub": str(admin_user.id)})
        response = system_client.get(
            "/system/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert "users" in body["data"]
