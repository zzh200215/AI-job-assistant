"""Standalone orchestration worker for redis_queue backend.

    cd backend && ./.venv/Scripts/python.exe -m scripts.run_orchestration_worker
"""

from __future__ import annotations

import signal
from threading import Event

from app.services.orchestration_runner import run_redis_worker


def main() -> int:
    stop_event = Event()

    def _stop(*_):
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    run_redis_worker(stop_event=stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
