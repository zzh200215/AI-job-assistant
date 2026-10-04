"""§10.15 的两条守卫：anyio 线程上限真的生效，且"能改成 `def` 的同会话 async 路由"确实见底了。

第 2 条是把 `scripts/scan_blocking_route_shapes.py` 的判据搬进测试：转换前后都跑过，
167 → 0；这条腿红就意味着有人新写了一条"体内没有 await 的 `async def` + 同步会话"路由——
那正是这次清掉的形状。
"""

from __future__ import annotations

import anyio.to_thread

from app.core.config import settings
from app.core.threadpool import apply_thread_limit, configured_thread_limit
from scripts.scan_blocking_route_shapes import scan


def test_the_thread_limit_is_the_pool_size_plus_overflow():
    assert configured_thread_limit() == max(1, int(settings.DB_POOL_SIZE)) + max(0, int(settings.DB_MAX_OVERFLOW))


def test_applying_the_limit_actually_moves_anyio():
    tokens = apply_thread_limit()
    assert anyio.to_thread.current_default_thread_limiter().total_tokens == tokens
    # 反向证据：换一个数进去，读出来必须跟着变——否则上面那行是在读空气
    apply_thread_limit(3)
    assert anyio.to_thread.current_default_thread_limiter().total_tokens == 3
    apply_thread_limit(tokens)
    assert anyio.to_thread.current_default_thread_limiter().total_tokens == tokens


def test_no_await_free_sync_session_routes_are_left():
    buckets = scan()
    convertible = sorted(f"{name}:{fn}" for name, info in buckets.items() for fn in info["convertible"])
    assert convertible == [], (
        f"这些路由拿着同步 db 会话、体内没有 await，却还是 `async def`（会把会话压在事件循环上）："
        f"{convertible}；改成 def，或说明为什么不能"
    )


def test_the_scanner_counts_the_awaiting_ones_as_untouchable():
    """剩下那 12 条**不能**改成 def：体内有 await。这条钉的是判据没把可转与不可转混成一桶。"""
    buckets = scan()
    awaiting = sum(len(info["awaits_something"]) for info in buckets.values())
    sync_async = sum(len(info["sync_session_async"]) for info in buckets.values())
    assert sync_async == awaiting, "同会话 async 路由应当只剩「有 await」的那些；多了就是有新写法进来"
    assert awaiting >= 1, "一条都不剩说明扫描判据失效（`app/api` 里不可能一个 await 都没有）"
