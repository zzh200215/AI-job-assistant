"""Standalone orchestration worker for redis_queue backend."""

from __future__ import annotations

import argparse
import signal
from threading import Event

from app.services.orchestration_runner import run_redis_worker


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standalone orchestration worker")
    parser.add_argument("--once", action="store_true", help="Process tasks until interrupted")
    args = parser.parse_args()

    stop_event = Event()

    def _stop(*_):
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    if args.once:
        run_redis_worker(stop_event=stop_event)
    else:
        run_redis_worker(stop_event=stop_event)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
