# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.auth import router as auth_router
from app.api.evaluation import router as evaluation_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.user import User


@pytest.fixture
def evaluation_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(evaluation_router, prefix="/eval-reports")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _write_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_eval_report_summary_and_list(evaluation_client, db_session, monkeypatch, tmp_path):
    from app.api import evaluation

    monkeypatch.setattr(evaluation, "REPORTS_DIR", tmp_path)

    _write_report(
        tmp_path / "rag_eval_20260626_120000.json",
        {
            "report_type": "rag",
            "total": 8,
            "recall@5": 0.91,
            "mrr": 0.88,
            "keyword_hit_rate": 0.79,
            "per_doc_type_recall": {"jd_lib": 1.0},
            "details": [{"query": "python"}],
            "run_meta": {"generated_at": "2026-06-26T12:00:00+00:00", "top_k": 5},
        },
    )
    _write_report(
        tmp_path / "agent_eval_20260626_120500.json",
        {
            "report_type": "agent",
            "total": 6,
            "mae": 4.2,
            "spearman_rho": 0.94,
            "score_dist": {"hit_tol10": 5, "over": 1, "under": 0},
            "details": [{"id": "pair_1"}],
            "run_meta": {"generated_at": "2026-06-26T12:05:00+00:00"},
        },
    )

    owner = _create_user(db_session, "eval_owner", "eval_owner@example.com")

    summary = evaluation_client.get("/eval-reports/summary", headers=_auth_headers(owner))
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["code"] == 0
    assert summary_body["data"]["total"] == 2
    assert summary_body["data"]["counts"]["rag"] == 1
    assert summary_body["data"]["latest_by_type"]["rag"]["metrics"]["recall"] == 0.91
    assert summary_body["data"]["latest_by_type"]["agent"]["metrics"]["mae"] == 4.2

    listing = evaluation_client.get(
        "/eval-reports/list",
        params={"report_type": "rag"},
        headers=_auth_headers(owner),
    )
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["code"] == 0
    assert listing_body["data"]["total"] == 1
    assert listing_body["data"]["items"][0]["report_type"] == "rag"
    assert listing_body["data"]["items"][0]["top_k"] == 5


def test_eval_report_detail_and_compare(evaluation_client, db_session, monkeypatch, tmp_path):
    from app.api import evaluation

    monkeypatch.setattr(evaluation, "REPORTS_DIR", tmp_path)

    _write_report(
        tmp_path / "agent_eval_a.json",
        {
            "report_type": "agent",
            "total": 10,
            "mae": 5.0,
            "spearman_rho": 0.91,
            "score_dist": {"hit_tol10": 7, "over": 2, "under": 1},
            "details": [{"id": "pair_a"}],
            "run_meta": {"generated_at": "2026-06-26T09:00:00+00:00"},
        },
    )
    _write_report(
        tmp_path / "agent_eval_b.json",
        {
            "report_type": "agent",
            "total": 10,
            "mae": 3.5,
            "spearman_rho": 0.95,
            "score_dist": {"hit_tol10": 8, "over": 1, "under": 1},
            "details": [{"id": "pair_b"}],
            "run_meta": {"generated_at": "2026-06-26T10:00:00+00:00"},
        },
    )

    owner = _create_user(db_session, "eval_compare_owner", "eval_compare_owner@example.com")

    detail = evaluation_client.get("/eval-reports/agent_eval_a.json", headers=_auth_headers(owner))
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["code"] == 0
    assert detail_body["data"]["summary"]["metrics"]["mae"] == 5.0
    assert detail_body["data"]["raw"]["score_dist"]["hit_tol10"] == 7

    compare = evaluation_client.get(
        "/eval-reports/compare",
        params={"report_a": "agent_eval_a.json", "report_b": "agent_eval_b.json"},
        headers=_auth_headers(owner),
    )
    assert compare.status_code == 200
    compare_body = compare.json()
    assert compare_body["code"] == 0
    assert compare_body["data"]["report_type"] == "agent"
    assert compare_body["data"]["delta"]["mae"] == -1.5
    assert compare_body["data"]["delta"]["hit_tol10"] == 1.0


def test_recommend_eval_report_summary_and_compare(evaluation_client, db_session, monkeypatch, tmp_path):
    from app.api import evaluation

    monkeypatch.setattr(evaluation, "REPORTS_DIR", tmp_path)

    _write_report(
        tmp_path / "recommend_eval_a.json",
        {
            "report_type": "recommend",
            "total": 4,
            "skill_match_accuracy": 0.81,
            "jd_explanation_consistency": 0.74,
            "recommendation_explainability": 0.78,
            "interview_score_stability": 0.88,
            "feedback_agreement_rate": 0.5,
            "online_feedback_linkage": {"linked_pair_count": 2, "linked_feedback_count": 4},
            "details": [{"id": "case_a"}],
            "run_meta": {"generated_at": "2026-06-26T08:00:00+00:00"},
        },
    )
    _write_report(
        tmp_path / "recommend_eval_b.json",
        {
            "report_type": "recommend",
            "total": 4,
            "skill_match_accuracy": 0.86,
            "jd_explanation_consistency": 0.8,
            "recommendation_explainability": 0.82,
            "interview_score_stability": 0.9,
            "feedback_agreement_rate": 1.0,
            "online_feedback_linkage": {"linked_pair_count": 3, "linked_feedback_count": 5},
            "details": [{"id": "case_b"}],
            "run_meta": {"generated_at": "2026-06-26T09:00:00+00:00"},
        },
    )

    owner = _create_user(db_session, "eval_recommend_owner", "eval_recommend_owner@example.com")

    summary = evaluation_client.get(
        "/eval-reports/summary",
        params={"report_type": "recommend"},
        headers=_auth_headers(owner),
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["code"] == 0
    assert summary_body["data"]["counts"]["recommend"] == 2
    assert summary_body["data"]["latest_by_type"]["recommend"]["metrics"]["skill_match_accuracy"] == 0.86

    compare = evaluation_client.get(
        "/eval-reports/compare",
        params={"report_a": "recommend_eval_a.json", "report_b": "recommend_eval_b.json"},
        headers=_auth_headers(owner),
    )
    assert compare.status_code == 200
    compare_body = compare.json()
    assert compare_body["code"] == 0
    assert compare_body["data"]["report_type"] == "recommend"
    assert compare_body["data"]["delta"]["skill_match_accuracy"] == 0.05
    assert compare_body["data"]["delta"]["feedback_agreement_rate"] == 0.5
