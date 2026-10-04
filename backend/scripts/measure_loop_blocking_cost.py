"""§10.19 的证据量具：把"同步原语压在事件循环里"这一族的代价量出来。

账上那 22 条（`INDIRECT_BLOCKING_ALLOWLIST`）分三族，这里用**真实原语**、只把外部落点换成本机桩
（不花 provider 钱、不需要真 MySQL）：

  A `http`     —— `requests.get` 打一台会睡 D 秒的本机 `ThreadingHTTPServer`（对应 `jd.import_jd_from_url`）
  B `provider` —— 同一个原语、同样的"一次请求 + 解析"形状（对应 resume/analysis 那 11 条 LLM 调用）
  C `db`       —— sqlite 上 12 次真实聚合查询（对应 D110 里"体内有 await、动不了"的那几条同步会话）

每族各测两种写法：`async def` 里直接调（=现状）与 `await run_in_threadpool(...)`（=改完）。
量的不是吞吐而是**别人的请求被拖多久**：并发打 N 条 `/control`（纯事件循环端点），中途放一发阻塞请求，
取 N 次重复里最坏的 p95 / max。

用法：PYTHONPATH=. python scripts/measure_loop_blocking_cost.py [--delay 0.35] [--ramps 1,5,20]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")

import httpx  # noqa: E402
import requests  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402


class _StubHandler(BaseHTTPRequestHandler):
    """假上游：路径最后一段是它要睡的毫秒数。"""

    def do_GET(self) -> None:  # noqa: N802
        delay = float(self.path.rsplit("/", 1)[-1] or "0") / 1000.0
        time.sleep(delay)
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _db_shaped() -> int:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (a int, b text)"))
        conn.execute(
            text("INSERT INTO t (a, b) VALUES (:a, :b)"),
            [{"a": i, "b": f"row-{i}"} for i in range(20000)],
        )
    total = 0
    with engine.connect() as conn:
        for _ in range(12):
            total += conn.execute(text("SELECT COUNT(a) FROM t WHERE a % 7 = 0")).scalar_one()
    engine.dispose()
    return total


def _build_app(block_ms: float, base_url: str) -> FastAPI:
    app = FastAPI()

    def http_blocking() -> dict:
        return requests.get(f"{base_url}/http/{block_ms}", timeout=10).json()

    def provider_shaped() -> dict:
        content = "x" * 400  # provider 那一族共同的多一次构造 + 解析
        del content
        return requests.get(f"{base_url}/http/{block_ms}", timeout=10).json()

    async def control(request):
        return JSONResponse({"ok": True})

    routes = {
        "http": (http_blocking, http_blocking),
        "provider": (provider_shaped, provider_shaped),
        "db": (_db_shaped, _db_shaped),
    }
    for kind, (fn, _) in routes.items():
        app.add_route(f"/{kind}/on-loop", _make_on_loop(fn), methods=["GET"])
        app.add_route(f"/{kind}/in-pool", _make_in_pool(fn), methods=["GET"])
    app.add_route("/control", control, methods=["GET"])
    return app


def _make_on_loop(fn):
    async def endpoint(request):
        return JSONResponse(fn())

    return endpoint


def _make_in_pool(fn):
    async def endpoint(request):
        return JSONResponse(await run_in_threadpool(fn))

    return endpoint


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


async def _timed(client: httpx.AsyncClient, path: str, dispatched_at: float) -> float:
    """`dispatched_at` 是调用方**发起那一刻**的时间戳。从协程内部取起点量不到排队——
    被同步代码卡住的协程根本还没开始执行（`tests/test_no_blocking_in_event_loop.py` 的
    `_latency_while_something_blocks` 注释里记过这同一个坑，本脚本第一版又踩了一遍）。"""
    await client.get(path)
    return time.perf_counter() - dispatched_at


async def _measure(app: FastAPI, kind: str, shape: str, concurrency: int) -> dict:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
        # 计时窗口从"两发都还没跑"起算（`_latency_while_something_blocks` 那条注释讲的同一个坑）：
        # 循环被同步代码占住时，被卡住的协程连自己的起点都还没执行，从里面量不到排队。
        dispatched = time.perf_counter()
        block_started = asyncio.ensure_future(_timed(client, f"/{kind}/{shape}", dispatched))
        await asyncio.sleep(0)  # 让阻塞那一发真的抢到循环
        controls = [asyncio.ensure_future(_timed(client, "/control", dispatched)) for _ in range(concurrency)]
        done = await asyncio.gather(*controls, block_started)
        latencies = done[:-1]
        blocker = done[-1]
    return {
        "control_p50": _percentile(latencies, 50) * 1000,
        "control_p95": _percentile(latencies, 95) * 1000,
        "control_max": max(latencies) * 1000,
        "blocker_ms": blocker * 1000,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.35, help="假上游每次睡多少秒")
    parser.add_argument("--ramps", default="1,5,20")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    app = _build_app(args.delay * 1000, base_url)

    rows = []
    for kind in ("http", "provider", "db"):
        for shape in ("on-loop", "in-pool"):
            for concurrency in [int(x) for x in args.ramps.split(",")]:
                samples = [asyncio.run(_measure(app, kind, shape, concurrency)) for _ in range(args.repeats)]
                rows.append(
                    {
                        "family": kind,
                        "shape": shape,
                        "concurrency": concurrency,
                        "worst_p50_ms": round(max(s["control_p50"] for s in samples), 1),
                        "worst_p95_ms": round(max(s["control_p95"] for s in samples), 1),
                        "worst_max_ms": round(max(s["control_max"] for s in samples), 1),
                        "blocker_ms": round(max(s["blocker_ms"] for s in samples), 1),
                    }
                )
    server.shutdown()
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
