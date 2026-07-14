"""统一重试工具

为网络型调用（LLM / Embedding / 外部 API）提供统一的重试、退避、日志策略，
避免在 base_agent、llm_service、embedding_service 中重复编写相同逻辑。

用法：
    @with_retry(max_retries=2, backoff_factor=1.5)
    def call_api(texts: List[str]) -> List[List[float]]:
        ...

或函数式：
    result = retry_call(fn, args=(texts,), max_retries=2)
"""

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def with_retry(
    max_retries: int = 2,
    backoff_factor: float = 1.5,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int, int], None] | None = None,
    log_prefix: str = "",
):
    """重试装饰器

    参数:
        max_retries:      最大重试次数（不含首次调用）
        backoff_factor:   退避基数，第 n 次等待 = backoff_factor * (attempt + 1)
        retryable_exceptions: 仅对这些异常重试，默认全部
        on_retry:         每次重试前的回调 fn(exc, attempt, max_retries)
        log_prefix:       日志前缀，便于区分不同调用方
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            last_err = None
            for attempt in range(1 + max_retries):
                try:
                    return fn(*args, **kwargs)
                except retryable_exceptions as e:
                    last_err = e
                    if attempt < max_retries:
                        wait = backoff_factor * (attempt + 1)
                        prefix = f"[{log_prefix}] " if log_prefix else ""
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
            raise RuntimeError(
                f"{log_prefix + ' ' if log_prefix else ''}调用失败（已重试 {max_retries} 次）: {last_err}"
            )

        return wrapper

    return decorator


def retry_call(
    fn: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    max_retries: int = 2,
    backoff_factor: float = 1.5,
    retryable_exceptions: tuple = (Exception,),
    log_prefix: str = "",
) -> Any:
    """函数式重试封装（不方便用装饰器时直接使用）"""
    kwargs = kwargs or {}
    last_err = None
    for attempt in range(1 + max_retries):
        try:
            return fn(*args, **kwargs)
        except retryable_exceptions as e:
            last_err = e
            if attempt < max_retries:
                wait = backoff_factor * (attempt + 1)
                prefix = f"[{log_prefix}] " if log_prefix else ""
                logger.warning(
                    f"{prefix}调用失败将重试(%d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                time.sleep(wait)
            else:
                break
    raise RuntimeError(f"{log_prefix + ' ' if log_prefix else ''}调用失败（已重试 {max_retries} 次）: {last_err}")
