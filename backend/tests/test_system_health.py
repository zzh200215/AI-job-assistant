"""System health, readiness, and metrics endpoint tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.system as system_api
from app.api.system import router as system_router
from app.core.config import settings
from app.core.database import get_db


def _system_client(db_session):
    app = FastAPI()
    app.include_router(system_router, prefix="/system")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(db_session):
    yield from _system_client(db_session)


class TestSystemHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/system/health")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "ok"

    def test_ready_returns_checks(self, client):
        response = client.get("/system/ready")
        # SQLite is used in tests, so MySQL check may report false; accept either 200 or 503.
        assert response.status_code in (200, 503)
        body = response.json()
        assert "ready" in body["data"]
        assert "checks" in body["data"]
        assert "mysql" in body["data"]["checks"]
        assert "chroma" in body["data"]["checks"]


class TestSystemMetricsAuth:
    """E1: `/system/metrics` used to answer any caller with no credentials at all.

    The payload carries provider/model names and degraded-answer counters, which is
    what A2 keeps off the candidate side — and `frontend/nginx.conf` proxies all of
    `/api/` to the backend, so under `docker-compose.prod.yml` the old behaviour was
    readable from the public internet.
    """

    def test_anonymous_caller_is_rejected(self, client):
        assert client.get("/system/metrics").status_code == 401

    def test_signed_in_candidate_is_rejected(self, client, normal_user, monkeypatch):
        monkeypatch.setattr(system_api, "get_current_user", lambda **kwargs: normal_user)
        assert client.get("/system/metrics", headers=_any_token()).status_code == 403

    def test_admin_session_gets_the_prometheus_payload(self, client, admin_user, monkeypatch):
        monkeypatch.setattr(system_api, "get_current_user", lambda **kwargs: admin_user)
        response = client.get("/system/metrics", headers=_any_token())
        assert response.status_code == 200
        assert "http_requests_total" in response.text

    def test_scrape_token_replaces_a_session(self, client, monkeypatch):
        """采集端没有会话可登，所以配了令牌就能凭令牌读。"""
        monkeypatch.setattr(settings, "METRICS_TOKEN", "scrape-token-value")
        response = client.get("/system/metrics", headers={"Authorization": "Bearer scrape-token-value"})
        assert response.status_code == 200
        assert "http_requests_total" in response.text

    def test_wrong_scrape_token_does_not_open_the_endpoint(self, client, monkeypatch):
        """令牌配好之后，拿错令牌的匿名调用方仍然进不来。"""
        monkeypatch.setattr(settings, "METRICS_TOKEN", "scrape-token-value")
        assert client.get("/system/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401


def _any_token() -> dict[str, str]:
    return {"Authorization": "Bearer session-token"}
