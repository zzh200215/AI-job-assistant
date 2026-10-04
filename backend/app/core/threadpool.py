"""anyio 线程池上限：让"并发取连接的线程数"不超过连接池能给的数量。

§10.15 把 167 条"体内没有 await、只拿着同步 SQLAlchemy 会话"的路由从 `async def` 改成 `def`
之后，FastAPI 会把它们丢进 anyio 的默认线程池。anyio 的默认上限是 **40 根线程**（本仓之前没设过），
而连接池是 `DB_POOL_SIZE + DB_MAX_OVERFLOW = 10 + 10 = 20` 个连接（E16 把那三个数从隐式默认
搬进了 `engine_kwargs_for`）。40 根线程抢 20 个连接时，多出来的一半会在 `pool_timeout`（30 秒）上
排队——那是"请求没超时但看起来死了"的形状，且只在并发高的时候出现。

所以这里把线程上限钉成连接池能给的数量：**没有线程会因为等连接而排队**，代价是超过 20 的并发请求
在 ASGI 层排队而不是在 SQLAlchemy 的等待队列里消失（排队是可观测的，等待不是）。
"""

from __future__ import annotations

import anyio
import anyio.to_thread

from app.core.config import settings


def configured_thread_limit() -> int:
    """= 连接池上限。至少 1，且 `DB_MAX_OVERFLOW=0` 时退化成 `DB_POOL_SIZE`。"""
    pool = max(1, int(settings.DB_POOL_SIZE))
    overflow = max(0, int(settings.DB_MAX_OVERFLOW))
    return pool + overflow


def apply_thread_limit(limit: int | None = None) -> int:
    """覆盖 anyio 的默认线程 limiter。返回真正生效的上限（幂等，可在测试里重复调用）。"""
    tokens = configured_thread_limit() if limit is None else max(1, int(limit))
    limiter = anyio.CapacityLimiter(tokens)
    anyio.to_thread.current_default_thread_limiter = lambda: limiter  # type: ignore[assignment]
    return tokens
