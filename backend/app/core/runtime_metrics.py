"""In-memory runtime metrics for lightweight observability."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

_LOCK = Lock()
_SLOW_REQUEST_MS = 1000
_METRICS = {
    "total_requests": 0,
    "error_requests": 0,
    "slow_requests": 0,
    "total_duration_ms": 0.0,
    "max_duration_ms": 0.0,
    "status_totals": {},
    "method_totals": {},
    "last_request_at": None,
}


def reset_runtime_metrics() -> None:
    with _LOCK:
        _METRICS["total_requests"] = 0
        _METRICS["error_requests"] = 0
        _METRICS["slow_requests"] = 0
        _METRICS["total_duration_ms"] = 0.0
        _METRICS["max_duration_ms"] = 0.0
        _METRICS["status_totals"] = {}
        _METRICS["method_totals"] = {}
        _METRICS["last_request_at"] = None


def record_request(*, method: str, status_code: int, duration_ms: float) -> None:
    status_key = str(status_code)
    with _LOCK:
        _METRICS["total_requests"] += 1
        if status_code >= 400:
            _METRICS["error_requests"] += 1
        if duration_ms >= _SLOW_REQUEST_MS:
            _METRICS["slow_requests"] += 1
        _METRICS["total_duration_ms"] += duration_ms
        _METRICS["max_duration_ms"] = max(_METRICS["max_duration_ms"], duration_ms)
        _METRICS["status_totals"][status_key] = _METRICS["status_totals"].get(status_key, 0) + 1
        method_key = (method or "UNKNOWN").upper()
        _METRICS["method_totals"][method_key] = _METRICS["method_totals"].get(method_key, 0) + 1
        _METRICS["last_request_at"] = datetime.now(timezone.utc).isoformat()


def get_runtime_metrics() -> dict:
    with _LOCK:
        total_requests = _METRICS["total_requests"]
        avg_duration_ms = _METRICS["total_duration_ms"] / total_requests if total_requests else 0.0
        return {
            "total_requests": total_requests,
            "error_requests": _METRICS["error_requests"],
            "slow_requests": _METRICS["slow_requests"],
            "avg_duration_ms": round(avg_duration_ms, 2),
            "max_duration_ms": round(_METRICS["max_duration_ms"], 2),
            "status_totals": dict(_METRICS["status_totals"]),
            "method_totals": dict(_METRICS["method_totals"]),
            "last_request_at": _METRICS["last_request_at"],
        }
