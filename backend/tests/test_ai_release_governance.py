"""Administrator AI release gate and cost attribution tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import evaluation
from app.api.system import router as system_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.prompt_trace import PromptTrace
from app.models.user import User


def _headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username, "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def _user(db_session, *, username: str, role: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("StrongP@ssw0rd"), role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _write_report(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_passing_reports(tmp_path) -> list[str]:
    generated_at = datetime.now(timezone.utc).isoformat()
    reports = {
        "rag_release.json": {
            "report_type": "rag",
            "total": 8,
            "recall@5": 0.92,
            "mrr": 0.88,
            "keyword_hit_rate": 0.81,
            "run_meta": {"generated_at": generated_at, "top_k": 5, "thresholds": {"min_recall": 0.9, "min_mrr": 0.8}},
        },
        "agent_release.json": {
            "report_type": "agent",
            "total": 8,
            "mae": 3.2,
            "spearman_rho": 0.91,
            "score_dist": {"hit_tol10": 7},
            "run_meta": {"generated_at": generated_at, "thresholds": {"max_mae": 5, "min_spearman": 0.85}},
        },
        "recommend_release.json": {
            "report_type": "recommend",
            "total": 8,
            "skill_match_accuracy": 0.87,
            "jd_explanation_consistency": 0.82,
            "recommendation_explainability": 0.8,
            "interview_score_stability": 0.9,
            "feedback_agreement_rate": 0.75,
            "run_meta": {
                "generated_at": generated_at,
                "thresholds": {"min_skill_match_accuracy": 0.8, "min_explanation_consistency": 0.8},
            },
        },
    }
    for name, payload in reports.items():
        _write_report(tmp_path / name, payload)
    return list(reports)


def test_ai_release_gate_approval_recheck_and_costs(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "REPORTS_DIR", tmp_path)
    report_ids = _write_passing_reports(tmp_path)
    app = FastAPI()
    app.include_router(system_router, prefix="/system")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = _user(db_session, username="release_admin", role="admin")
    candidate = _user(db_session, username="release_candidate", role="candidate")
    db_session.add(
        PromptTrace(
            request_id="release-cost-trace",
            source="match_service.analyze",
            prompt_version="match-v3",
            provider="openai",
            model="gpt-4.1-mini",
            status="success",
            prompt_tokens=300,
            completion_tokens=200,
            total_tokens=500,
            cost_cents=1.25,
            user_id=admin.id,
        )
    )
    db_session.commit()

    payload = {"release_key": "2026-07-match-v3", "prompt_versions": ["match-v3"], "evaluation_report_ids": report_ids}
    with TestClient(app) as client:
        denied = client.post("/system/ai-releases", json=payload, headers=_headers(candidate))
        assert denied.status_code == 403

        created = client.post("/system/ai-releases", json=payload, headers=_headers(admin))
        assert created.status_code == 200
        release = created.json()["data"]
        assert release["status"] == "ready"
        assert release["gate_result"]["passed"] is True
        assert len(release["evaluation_reports"]) == 3

        approved = client.post(f"/system/ai-releases/{release['id']}/approve", headers=_headers(admin))
        assert approved.status_code == 200
        assert approved.json()["data"]["status"] == "approved"

        costs = client.get("/system/ai-costs", headers=_headers(admin))
        assert costs.status_code == 200
        assert costs.json()["data"]["total_cost_cents"] == 1.25
        assert costs.json()["data"]["items"][0]["prompt_version"] == "match-v3"

        agent_path = tmp_path / "agent_release.json"
        agent_report = json.loads(agent_path.read_text(encoding="utf-8"))
        agent_report["mae"] = 9.0
        _write_report(agent_path, agent_report)

        rechecked = client.post(f"/system/ai-releases/{release['id']}/evaluate", headers=_headers(admin))
        assert rechecked.status_code == 200
        assert rechecked.json()["data"]["status"] == "blocked"
        assert rechecked.json()["data"]["gate_result"]["passed"] is False

        blocked = client.post(f"/system/ai-releases/{release['id']}/approve", headers=_headers(admin))
        assert blocked.status_code == 409


def test_ai_release_blocks_report_without_explicit_thresholds(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "REPORTS_DIR", tmp_path)
    report_ids = _write_passing_reports(tmp_path)
    rag_path = tmp_path / "rag_release.json"
    rag_report = json.loads(rag_path.read_text(encoding="utf-8"))
    rag_report["run_meta"]["thresholds"] = {}
    _write_report(rag_path, rag_report)
    app = FastAPI()
    app.include_router(system_router, prefix="/system")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = _user(db_session, username="threshold_admin", role="admin")
    payload = {"release_key": "threshold-blocked", "prompt_versions": ["rag-v2"], "evaluation_report_ids": report_ids}

    with TestClient(app) as client:
        response = client.post("/system/ai-releases", json=payload, headers=_headers(admin))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "blocked"
    assert any("未声明发布阈值" in item for item in data["gate_result"]["failures"])
