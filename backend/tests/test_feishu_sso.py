"""Feishu organization SSO tests with mocked provider responses."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.organization import router as organization_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.user import User


def _owner(db) -> User:
    user = User(username="feishu_owner", email="feishu_owner@example.com", password=hash_password("StrongP@ssw0rd"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'email': user.email, 'username': user.username})}"
    }


def test_feishu_sso_start_and_callback_provisions_member(db_session, monkeypatch):
    from app.api import organization as organization_api

    app = FastAPI()
    app.include_router(organization_router, prefix="/organizations")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(organization_api.settings, "FEISHU_APP_ID", "cli_test")
    monkeypatch.setattr(organization_api.settings, "FEISHU_APP_SECRET", "secret")
    monkeypatch.setattr(organization_api.settings, "FEISHU_REDIRECT_URI", "https://example.test/callback")

    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": self.data}

    monkeypatch.setattr(
        organization_api.requests, "post", lambda *args, **kwargs: FakeResponse({"access_token": "token"})
    )
    monkeypatch.setattr(
        organization_api.requests,
        "get",
        lambda *args, **kwargs: FakeResponse({"union_id": "union-user-1", "email": "new.feishu@example.com"}),
    )
    owner = _owner(db_session)

    with TestClient(app) as client:
        organization = client.post(
            "/organizations", json={"name": "Feishu Team", "slug": "feishu-team"}, headers=_headers(owner)
        ).json()["data"]
        configured = client.put(
            f"/organizations/{organization['id']}/sso", json={"provider": "feishu"}, headers=_headers(owner)
        )
        assert configured.status_code == 200

        start = client.get("/organizations/sso/feishu/feishu-team/start", follow_redirects=False)
        assert start.status_code == 302
        assert "accounts.feishu.cn" in start.headers["location"]
        state = start.headers["location"].split("state=", 1)[1]

        callback = client.get("/organizations/sso/feishu/callback", params={"code": "grant-code", "state": state})
        assert callback.status_code == 200
        data = callback.json()["data"]
        assert data["user"]["email"] == "new.feishu@example.com"

        callback_again = client.get("/organizations/sso/feishu/callback", params={"code": "grant-code", "state": state})
        assert callback_again.status_code == 400
