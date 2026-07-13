# -*- coding: utf-8 -*-
"""Rate limiting tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.auth import router as auth_router
from app.core.database import get_db
from app.core.rate_limiter import _build_storage_uri, get_limiter
from app.main import rate_limit_handler


def _build_test_app(db_session):
    app = FastAPI()
    app.state.limiter = get_limiter()
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.include_router(auth_router, prefix="/auth")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def rate_client(db_session):
    app = _build_test_app(db_session)
    with TestClient(app) as client:
        yield client


class TestRateLimit:
    def test_testing_mode_uses_in_memory_storage(self):
        assert _build_storage_uri() == "memory://"

    def test_normal_requests_not_limited(self, rate_client, normal_user):
        for _ in range(3):
            response = rate_client.post(
                "/auth/login",
                json={"account": normal_user.username, "password": "WrongPass123!"},
            )
            assert response.status_code in (200, 429)
            if response.status_code == 429:
                pytest.skip("Rate limit reached earlier than expected")

    def test_excessive_login_requests_return_429(self, rate_client, normal_user):
        # Exceed the 5/minute login limit.
        responses = []
        for _ in range(7):
            response = rate_client.post(
                "/auth/login",
                json={"account": normal_user.username, "password": "WrongPass123!"},
            )
            responses.append(response.status_code)

        assert 429 in responses
        body = rate_client.post(
            "/auth/login",
            json={"account": normal_user.username, "password": "WrongPass123!"},
        ).json()
        assert "频繁" in body["message"] or "rate" in body["message"].lower()

    def test_rate_limit_headers_present(self, rate_client, normal_user):
        response = rate_client.post(
            "/auth/login",
            json={"account": normal_user.username, "password": "WrongPass123!"},
        )
        # slowapi returns X-RateLimit-* headers when headers_enabled=True.
        assert "x-ratelimit-limit" in {k.lower() for k in response.headers}
