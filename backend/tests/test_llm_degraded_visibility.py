"""A2: degraded LLM responses must be queryable internally and alertable.

The product decision is that candidates are *not* shown a degraded badge, so the
operations side is the only channel that can notice fabricated content reaching
results. These tests pin that channel.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.prometheus_metrics import REGISTRY
from app.core.security import hash_password
from app.models.prompt_trace import PromptTrace
from app.models.user import User
from app.services import prompt_trace_service
from app.services.operational_alert_service import collect_operational_alerts
from app.utils.time_helper import utc_now

_SNAPSHOT_OK = {
    "model_runtime": {"ready": True, "llm": {"mode": "live"}, "embedding": {"mode": "live"}},
    "queue_health": {"ok": True, "backend": "thread", "queue_length": 0},
    "runtime_metrics": {"total_requests": 0, "error_requests": 0},
}


_TRACE_SEQ = {"n": 0}


def _trace(db, user, *, response_source: str, degraded: bool, status: str = "success") -> PromptTrace:
    _TRACE_SEQ["n"] += 1
    row = PromptTrace(
        request_id=f"req-a2-{_TRACE_SEQ['n']}",
        source="tests",
        provider="qwen",
        model="qwen-turbo",
        response_source=response_source,
        degraded=int(degraded),
        status=status,
        user_id=user.id,
        created_at=utc_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _user(db) -> User:
    user = User(
        username="a2_ops",
        email="a2_ops@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_record_prompt_trace_derives_degraded_from_source(db_session):
    """Callers that forget `degraded=` must still get a truthful row."""
    user = _user(db_session)
    trace = prompt_trace_service.record_prompt_trace(
        prompt="p",
        response_text="{}",
        response_json={},
        provider="qwen",
        model="qwen-turbo",
        response_source="mock",
        user_id=user.id,
        db=db_session,
    )
    assert trace.degraded == 1

    real = prompt_trace_service.record_prompt_trace(
        prompt="p2",
        response_text="{}",
        response_json={},
        provider="qwen",
        model="qwen-turbo",
        response_source="real",
        user_id=user.id,
        db=db_session,
    )
    assert real.degraded == 0


def test_summary_metrics_report_degraded_breakdown(db_session):
    from app.api.prompt_trace import _metrics_from_rows

    user = _user(db_session)
    rows = [
        _trace(db_session, user, response_source="real", degraded=False),
        _trace(db_session, user, response_source="mock", degraded=True),
        _trace(db_session, user, response_source="truncated", degraded=True),
        _trace(db_session, user, response_source="truncated", degraded=True),
    ]
    metrics = _metrics_from_rows(rows)

    assert metrics["total"] == 4
    assert metrics["degraded_count"] == 3
    assert metrics["degraded_rate"] == 0.75
    assert metrics["degraded_by_source"] == {"mock": 1, "truncated": 2}


def test_query_rows_can_filter_to_degraded_only(db_session):
    from app.api.prompt_trace import _query_rows

    user = _user(db_session)
    _trace(db_session, user, response_source="real", degraded=False)
    degraded_row = _trace(db_session, user, response_source="mock", degraded=True)

    only_degraded = _query_rows(db_session, user_id=user.id, degraded=True)
    assert [row.id for row in only_degraded] == [degraded_row.id]

    by_source = _query_rows(db_session, user_id=user.id, response_source="truncated")
    assert by_source == []


def test_degraded_responses_raise_an_alert(db_session):
    user = _user(db_session)
    for _ in range(3):
        _trace(db_session, user, response_source="truncated", degraded=True)
    _trace(db_session, user, response_source="real", degraded=False)

    alerts = collect_operational_alerts(db_session, **_SNAPSHOT_OK)
    by_key = {a["alert_key"]: a for a in alerts}

    assert "llm_degraded_responses" in by_key
    alert = by_key["llm_degraded_responses"]
    # no mock involved -> warning, not critical
    assert alert["severity"] == "warning"
    assert alert["context"]["degraded_calls"] == 3


def test_mock_response_alerts_on_its_own(db_session):
    """One mock reply is already fabricated content served to a candidate."""
    user = _user(db_session)
    _trace(db_session, user, response_source="mock", degraded=True)

    alerts = collect_operational_alerts(db_session, **_SNAPSHOT_OK)
    by_key = {a["alert_key"]: a for a in alerts}

    assert "llm_mock_responses_served" in by_key
    alert = by_key["llm_mock_responses_served"]
    assert alert["severity"] == "critical"
    assert alert["context"]["mock_calls"] == 1
    assert alert["context"]["by_source"] == {"mock": 1}
    # the volume-based warning must not double-fire alongside it
    assert "llm_degraded_responses" not in by_key


def test_degraded_and_mock_alerts_are_mutually_exclusive(db_session):
    user = _user(db_session)
    for _ in range(4):
        _trace(db_session, user, response_source="truncated", degraded=True)
    _trace(db_session, user, response_source="mock", degraded=True)

    keys = {a["alert_key"] for a in collect_operational_alerts(db_session, **_SNAPSHOT_OK)}
    assert "llm_mock_responses_served" in keys
    assert "llm_degraded_responses" not in keys


def test_old_traces_outside_the_window_do_not_alert(db_session):
    user = _user(db_session)
    row = _trace(db_session, user, response_source="mock", degraded=True)
    row.created_at = utc_now() - timedelta(days=2)
    db_session.commit()

    alerts = collect_operational_alerts(db_session, **_SNAPSHOT_OK)
    assert "llm_mock_responses_served" not in {a["alert_key"] for a in alerts}


def test_degraded_and_trace_failure_counters_exist():
    """The alerting layer reads these; a missing label would only fail at runtime."""
    from app.core import prometheus_metrics as m

    m.record_llm_degraded_response(provider="qwen", model="qwen-turbo", response_source="mock")
    m.record_prompt_trace_write_failure("chat_json")

    degraded = REGISTRY.get_sample_value(
        "llm_degraded_responses_total",
        {"provider": "qwen", "model": "qwen-turbo", "response_source": "mock"},
    )
    failures = REGISTRY.get_sample_value(
        "prompt_trace_write_failures_total", {"stage": "chat_json"}
    )
    assert degraded is not None and degraded >= 1
    assert failures is not None and failures >= 1
