"""Operational alert lifecycle and administrator API tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import system
from app.api.auth import router as auth_router
from app.api.system import router as system_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.operational_alert import OperationalAlert
from app.models.user import User
from app.services.operational_alert_service import evaluate_operational_alerts


def _snapshot(*, ready: bool) -> dict:
    return {
        "model_runtime": {
            "ready": ready,
            "llm": {"mode": "live" if ready else "misconfigured"},
            "embedding": {"mode": "live"},
        },
        "queue_health": {"ok": True, "backend": "thread", "queue_length": 0},
        "runtime_metrics": {"total_requests": 0, "error_requests": 0},
    }


def _headers(user: User) -> dict:
    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "username": user.username, "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


def _create_user(db_session, *, username: str, role: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("StrongP@ssw0rd"), role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_evaluation_deduplicates_and_resolves_alerts(db_session):
    first = evaluate_operational_alerts(db_session, **_snapshot(ready=False))
    second = evaluate_operational_alerts(db_session, **_snapshot(ready=False))

    assert len(first) == 1
    assert len(second) == 1
    alert = db_session.query(OperationalAlert).one()
    assert alert.alert_key == "model_runtime_unavailable"
    assert alert.occurrences == 2
    assert alert.status == "open"

    current = evaluate_operational_alerts(db_session, **_snapshot(ready=True))

    assert current == []
    db_session.refresh(alert)
    assert alert.status == "resolved"
    assert alert.resolved_at is not None


def test_alert_endpoints_require_admin_and_record_acknowledgement(db_session, monkeypatch):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(system_router, prefix="/system")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = _create_user(db_session, username="alert_admin", role="admin")
    candidate = _create_user(db_session, username="alert_candidate", role="candidate")
    monkeypatch.setattr(system, "build_operational_alert_snapshot", lambda: _snapshot(ready=False))

    with TestClient(app) as client:
        denied = client.post("/system/alerts/evaluate", headers=_headers(candidate))
        assert denied.status_code == 403

        evaluated = client.post("/system/alerts/evaluate", headers=_headers(admin))
        assert evaluated.status_code == 200
        alert = evaluated.json()["data"]["alerts"][0]
        assert alert["alert_key"] == "model_runtime_unavailable"

        acknowledged = client.post(f"/system/alerts/{alert['id']}/acknowledge", headers=_headers(admin))
        assert acknowledged.status_code == 200
        data = acknowledged.json()["data"]
        assert data["status"] == "acknowledged"
        assert data["acknowledged_by"] == admin.id

        listing = client.get("/system/alerts", headers=_headers(admin))
        assert listing.status_code == 200
        assert listing.json()["data"]["alerts"][0]["status"] == "acknowledged"
