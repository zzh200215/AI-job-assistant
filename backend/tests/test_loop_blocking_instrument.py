"""§10.19 量具的自检：`measure_loop_blocking_cost.py` 必须看得见停摆，也必须看得见修好。

这台量具在本轮里错过两次，两次都是同一个方向：计时起点取在被卡住的协程**内部**，于是阻塞期间
它根本还没开始跑，量到的"对照请求 p95"永远是 0.x 毫秒——一个看起来"全绿"的假测量。
（`tests/test_no_blocking_in_event_loop.py::_latency_while_something_blocks` 的注释早就记着这同一个坑，
我还是踩了两遍。）所以这条测试钉的不是性能数字，是**量具的两端**：
现状形状必须量出接近上游延迟的排队，包进线程池之后必须量不出来。
"""

from __future__ import annotations

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

import scripts.measure_loop_blocking_cost as harness

UPSTREAM_MS = 220


def test_the_instrument_sees_a_stall_and_sees_the_fix() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        app = _tiny_app(base)
        on_loop = asyncio.run(harness._measure(app, "probe", "on-loop", 3))
        in_pool = asyncio.run(harness._measure(app, "probe", "in-pool", 3))
    finally:
        server.shutdown()

    assert on_loop["blocker_ms"] >= UPSTREAM_MS * 0.8, f"上游桩没生效：{on_loop}"
    assert on_loop["control_p95"] >= UPSTREAM_MS * 0.8, (
        f"量具看不见停摆：对照请求只等了 {on_loop['control_p95']:.1f}ms，"
        f"而上游睡了 {UPSTREAM_MS}ms——十次有十次是计时起点取错了"
    )
    assert in_pool["control_p95"] < UPSTREAM_MS * 0.5, (
        f"包进线程池之后对照请求仍要等 {in_pool['control_p95']:.1f}ms，"
        "那这台量具就无法区分两种形状，D111 的证据表全部作废"
    )


class _Stub(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        time.sleep(UPSTREAM_MS / 1000.0)
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _tiny_app(base: str) -> FastAPI:
    import requests

    app = FastAPI()

    def blocking() -> dict:
        return requests.get(f"{base}/http/1", timeout=10).json()

    async def on_loop(request):
        return JSONResponse(blocking())

    async def in_pool(request):
        return JSONResponse(await run_in_threadpool(blocking))

    async def control(request):
        return JSONResponse({"ok": True})

    app.add_route("/probe/on-loop", on_loop, methods=["GET"])
    app.add_route("/probe/in-pool", in_pool, methods=["GET"])
    app.add_route("/control", control, methods=["GET"])
    return app


def test_the_measure_helper_signature_is_the_shared_one() -> None:
    """`_measure` 的签名一变，上面那条就只是在读旧数字。这条把耦合钉住。"""
    import inspect

    params = list(inspect.signature(harness._measure).parameters)
    assert params == ["app", "kind", "shape", "concurrency"], params
    assert "dispatched" in inspect.getsource(harness._timed), "计时起点又退回协程内部了"
