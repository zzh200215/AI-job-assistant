# -*- coding: utf-8 -*-
"""System health, readiness, and metrics endpoint tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system import router as system_router
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

    def test_metrics_returns_prometheus_format(self, client):
        response = client.get("/system/metrics")
        assert response.status_code == 200
        content = response.text
        assert "http_requests_total" in content
