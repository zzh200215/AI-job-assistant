"""按用户计量**真实** provider 调用（E28）。

§10.10 的决策是"只给昂贵端点独立额度"。装在哪一层是这次先量出来的结论：请求内同步花钱的只有 4 条
resume 路由，而**入队之后在 worker 里花的钱更多**（一次 linear 编排实测 12 个 agent / 13 个 chat 调用点，
约 ≤11 次 provider 调用）。所以在路由上加额度要选 8 个入口、还漏掉整条后台路径；这里选的是
**出口一处计量**：`llm_service` 真发请求之前扣一次。

三条设计约定都写在这儿，因为它们各自都能悄悄造成误伤：

* **只计真花钱的**：`LLM_PROVIDER=mock` 时完全不扣 —— 否则整个测试套件会被一个额度闸拦掉。
* **认不出用户就不扣（fail-open）**：计费身份走 `ContextVar`。`logging_utils` 那套上下文用的是
  `threading.local`，跨线程（`ThreadPoolExecutor` 起的编排 worker）取不到，所以不能拿它当身份源。
  没设到身份的请求宁可不限，也不要变成"所有人的调用记在第一个人头上"。
* **额度存储自己坏了也 fail-open**：Redis 抖动不应该让正常请求变成 429。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from app.core.config import settings

logger = logging.getLogger(__name__)

_BILLING_KEY: ContextVar[str | None] = ContextVar("llm_billing_key", default=None)

_strategy = None
_storage_error_logged = False


class LLMQuotaExceededError(RuntimeError):
    """某用户在窗口内的真实 provider 调用数超预算。不是"可重试的 provider 故障"，
    所以调用方的降级/重试链不能吞它。"""


def set_billing_user(user_id: int | str | None) -> None:
    """给当前执行上下文设定计费身份。重复设置是幂等的（同一请求里 `get_current_user` 可能被走多次）。"""
    if user_id is None or user_id == "":
        return
    _BILLING_KEY.set(f"user:{user_id}")


def billing_key() -> str | None:
    return _BILLING_KEY.get()


def reset_for_tests() -> None:
    """测试用：丢掉缓存的策略与"存储坏了"的一次性日志标记。"""
    global _strategy, _storage_error_logged
    _strategy = None
    _storage_error_logged = False
    _BILLING_KEY.set(None)


def _limit_per_minute() -> int:
    return max(0, int(settings.LLM_CALLS_PER_USER_PER_MINUTE or 0))


def _get_strategy():
    global _strategy
    if _strategy is not None:
        return _strategy
    from limits.strategies import FixedWindowRateLimiter

    if settings.REDIS_URL:
        from limits.storage import RedisStorage

        storage = RedisStorage(settings.REDIS_URL)
    else:
        from limits.storage import MemoryStorage

        storage = MemoryStorage()
    _strategy = FixedWindowRateLimiter(storage)
    return _strategy


def charge_if_real_provider(*, provider: str | None = None) -> None:
    """真 provider 调用前扣一格。超预算抛 `LLMQuotaExceededError`。"""
    global _storage_error_logged
    if (provider or settings.LLM_PROVIDER or "mock").strip().lower() in {"", "mock"}:
        return
    limit = _limit_per_minute()
    key = _BILLING_KEY.get()
    if limit <= 0 or key is None:
        return
    try:
        from limits import parse

        allowed = _get_strategy().hit(parse(f"{limit}/minute"), key)
    except Exception as exc:  # noqa: BLE001 - 额度机制坏了不能让业务变成 429
        if not _storage_error_logged:
            _storage_error_logged = True
            logger.exception("LLM 额度存储不可用，本次与后续按不限处理（fail-open）: %s", exc)
        return
    if not allowed:
        raise LLMQuotaExceededError(f"该账号一分钟内已用满 {limit} 次模型调用额度，请稍后再试")
