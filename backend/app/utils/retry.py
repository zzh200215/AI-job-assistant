"""统一重试工具

为网络型调用（LLM / Embedding / 智能体节点）提供唯一一份重试、退避、日志实现。

用法：
    result = retry_call(fn, args=(texts,), max_retries=2, on_retry=cb)

`on_retry(exc, attempt, max_retries)` 在每次退避前回调，供调用方记录重试次数或
回滚共享事务——装饰器版与函数版曾是两份实现，`retry_call` 少了 `on_retry`，
调用方传了就 TypeError，所以只剩一份。
"""

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def retry_call(
    fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    max_retries: int = 2,
    backoff_factor: float = 1.5,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int, int], None] | None = None,
    log_prefix: str = "",
) -> Any:
    """调用 fn，失败时最多重试 max_retries 次（不含首次）。

    重试用尽仍失败时抛 RuntimeError，原始异常保留在 __cause__。
    """
    kwargs = kwargs or {}
    prefix = f"[{log_prefix}] " if log_prefix else ""
    last_err: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            return fn(*args, **kwargs)
        except retryable_exceptions as e:
            last_err = e
            if attempt < max_retries:
                wait = backoff_factor * (attempt + 1)
                logger.warning(
                    f"{prefix}调用失败将重试(%d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if on_retry:
                    on_retry(e, attempt, max_retries)
                time.sleep(wait)
            else:
                break
    raise RuntimeError(f"{prefix}调用失败（已重试 {max_retries} 次）: {last_err}") from last_err
