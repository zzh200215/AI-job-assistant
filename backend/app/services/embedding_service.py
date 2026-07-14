"""
Embedding 服务 — 可替换接口

当前实现：
  1. mock        — 返回随机向量（仅用于开发测试）
  2. dashscope   — 通过阿里云 千问 API 获取 embedding
  3. openai      — OpenAI 兼容协议 embedding

通过环境变量 EMBEDDING_PROVIDER 切换，默认 mock。
"""

import hashlib
import logging
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.prometheus_metrics import record_embedding_error, record_embedding_request
from app.models.embedding_usage import EmbeddingUsageDaily
from app.utils.retry import retry_call

logger = logging.getLogger(__name__)

# 网络型 embedding 单次请求的最大文本条数
# （dashscope text-embedding-v3 上限为 10；取 10 通用兼容）
_EMBED_BATCH_SIZE = 10


class EmbeddingProviderError(Exception):
    """Embedding provider 错误基类"""

    pass


class EmbeddingTimeoutError(EmbeddingProviderError):
    """Embedding 调用超时"""

    pass


class EmbeddingAuthError(EmbeddingProviderError):
    """Embedding 鉴权失败"""

    pass


# ===================== Embedding 结果缓存 =====================
# 相同文本（同一 provider+model）直接复用上次向量，避免重复调用 embedding API。
# 进程内 LRU；命中后可显著降低时延与 token 成本。
_EMBED_CACHE: "OrderedDict[str, list[float]]" = OrderedDict()
_EMBED_CACHE_MAX = 512
_EMBED_CACHE_LOCK = threading.Lock()
_EMBED_STATS_LOCK = threading.Lock()
_EMBED_STATS = {
    "total_calls": 0,
    "total_texts": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "network_batches": 0,
    "provider_totals": {},
    "model_totals": {},
    "last_call_at": None,
}
_EMBED_STATS_SESSION_FACTORY = SessionLocal


def _embed_cache_key(provider: str, text: str) -> str:
    raw = f"{provider}|{settings.EMBEDDING_MODEL or 'default'}|{text}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def clear_embed_cache() -> None:
    """清空 embedding 缓存（测试或模型切换时用）。"""
    with _EMBED_CACHE_LOCK:
        _EMBED_CACHE.clear()


def reset_embedding_stats() -> None:
    """重置 embedding 运行时统计（测试用）。"""
    with _EMBED_STATS_LOCK:
        _EMBED_STATS["total_calls"] = 0
        _EMBED_STATS["total_texts"] = 0
        _EMBED_STATS["cache_hits"] = 0
        _EMBED_STATS["cache_misses"] = 0
        _EMBED_STATS["network_batches"] = 0
        _EMBED_STATS["provider_totals"] = {}
        _EMBED_STATS["model_totals"] = {}
        _EMBED_STATS["last_call_at"] = None


def get_embedding_stats() -> dict:
    """获取 embedding 运行时聚合统计。"""
    with _EMBED_STATS_LOCK:
        return {
            "total_calls": _EMBED_STATS["total_calls"],
            "total_texts": _EMBED_STATS["total_texts"],
            "cache_hits": _EMBED_STATS["cache_hits"],
            "cache_misses": _EMBED_STATS["cache_misses"],
            "network_batches": _EMBED_STATS["network_batches"],
            "cache_hit_rate": round(
                (_EMBED_STATS["cache_hits"] / _EMBED_STATS["total_texts"]) if _EMBED_STATS["total_texts"] else 0.0,
                4,
            ),
            "provider_totals": dict(_EMBED_STATS["provider_totals"]),
            "model_totals": dict(_EMBED_STATS["model_totals"]),
            "last_call_at": _EMBED_STATS["last_call_at"],
        }


def set_embedding_stats_session_factory(factory) -> None:
    """Override session factory used by persistent embedding stats."""
    global _EMBED_STATS_SESSION_FACTORY
    _EMBED_STATS_SESSION_FACTORY = factory


def get_embedding_daily_stats(days: int = 7) -> list[dict]:
    """读取最近 N 天 embedding 日聚合统计。"""
    session = _EMBED_STATS_SESSION_FACTORY()
    try:
        rows = (
            session.query(EmbeddingUsageDaily)
            .order_by(
                EmbeddingUsageDaily.stat_date.desc(),
                EmbeddingUsageDaily.provider.asc(),
                EmbeddingUsageDaily.model.asc(),
            )
            .limit(max(days, 1) * 20)
            .all()
        )
        return [
            {
                "stat_date": row.stat_date.isoformat(),
                "provider": row.provider,
                "model": row.model,
                "total_calls": row.total_calls,
                "total_texts": row.total_texts,
                "cache_hits": row.cache_hits,
                "cache_misses": row.cache_misses,
                "network_batches": row.network_batches,
                "cache_hit_rate": round((row.cache_hits / row.total_texts) if row.total_texts else 0.0, 4),
            }
            for row in rows
        ]
    finally:
        session.close()


def _persist_embedding_daily_stats(
    *,
    provider: str,
    model: str,
    total_texts: int,
    cache_hits: int,
    cache_misses: int,
    batch_count: int,
) -> None:
    session = _EMBED_STATS_SESSION_FACTORY()
    stat_date = datetime.now(timezone.utc).date()
    try:
        row = (
            session.query(EmbeddingUsageDaily)
            .filter(
                EmbeddingUsageDaily.stat_date == stat_date,
                EmbeddingUsageDaily.provider == provider,
                EmbeddingUsageDaily.model == model,
            )
            .first()
        )
        if row is None:
            row = EmbeddingUsageDaily(
                stat_date=stat_date,
                provider=provider,
                model=model,
                total_calls=0,
                total_texts=0,
                cache_hits=0,
                cache_misses=0,
                network_batches=0,
            )
            session.add(row)

        row.total_calls += 1
        row.total_texts += total_texts
        row.cache_hits += cache_hits
        row.cache_misses += cache_misses
        row.network_batches += batch_count
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist embedding daily stats")
    finally:
        session.close()


def _record_embedding_stats(
    *,
    provider: str,
    model: str,
    total_texts: int,
    cache_hits: int,
    cache_misses: int,
    batch_count: int,
) -> None:
    with _EMBED_STATS_LOCK:
        _EMBED_STATS["total_calls"] += 1
        _EMBED_STATS["total_texts"] += total_texts
        _EMBED_STATS["cache_hits"] += cache_hits
        _EMBED_STATS["cache_misses"] += cache_misses
        _EMBED_STATS["network_batches"] += batch_count
        _EMBED_STATS["provider_totals"][provider] = _EMBED_STATS["provider_totals"].get(provider, 0) + total_texts
        _EMBED_STATS["model_totals"][model] = _EMBED_STATS["model_totals"].get(model, 0) + total_texts
        _EMBED_STATS["last_call_at"] = datetime.now(timezone.utc).isoformat()
    _persist_embedding_daily_stats(
        provider=provider,
        model=model,
        total_texts=total_texts,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        batch_count=batch_count,
    )


def _log_embedding_stats(
    *,
    provider: str,
    model: str,
    total_texts: int,
    cache_hits: int,
    cache_misses: int,
    batch_count: int,
) -> None:
    """记录 embedding 调用规模与缓存命中情况，便于追踪成本。"""
    _record_embedding_stats(
        provider=provider,
        model=model,
        total_texts=total_texts,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        batch_count=batch_count,
    )
    logger.info(
        "Embedding stats provider=%s model=%s total=%d cache_hits=%d cache_misses=%d batches=%d",
        provider,
        model,
        total_texts,
        cache_hits,
        cache_misses,
        batch_count,
    )


def _with_retry(fn, texts: list[str]) -> list[list[float]]:
    """对网络型 embedding 调用做有限次重试 + 退避。"""
    return retry_call(
        fn,
        args=(texts,),
        max_retries=max(0, settings.EMBEDDING_MAX_RETRIES),
        log_prefix="Embedding",
    )


def _mock_embedding_dimension(model: str) -> int:
    normalized = (model or "").strip().lower()
    if normalized == "text-embedding-v3":
        return 1024
    if normalized in {"text-embedding-3-large"}:
        return 3072
    if normalized in {"text-embedding-3-small", "text-embedding-ada-002"}:
        return 1536
    return 512


def _mock_embed(text: str, dimension: int | None = None) -> list[float]:
    """
    基于文本 hash 生成伪 embedding（仅测试用）。
    相同文本返回相同向量，保证检索可复现。
    """
    if dimension is None:
        dimension = _mock_embedding_dimension(settings.EMBEDDING_MODEL or "")

    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    seed = int(h[:8], 16)
    # 用确定性方式生成 dimension 个浮点数
    vec = []
    r = seed
    for _ in range(dimension):
        r = (r * 1103515245 + 12345) & 0x7FFFFFFF
        vec.append((r % 20000) / 10000.0 - 1.0)  # [-1, 1]
    # L2 归一化
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _dashscope_embed(texts: list[str]) -> list[list[float]]:
    """通过阿里云 千问 embedding API"""
    try:
        from dashscope import TextEmbedding
    except ImportError as exc:
        raise EmbeddingProviderError("请安装 dashscope: pip install dashscope") from exc

    model = settings.EMBEDDING_MODEL or "text-embedding-v3"
    resp = TextEmbedding.call(
        model=model,
        input=texts,
        api_key=settings.EMBEDDING_API_KEY or settings.LLM_API_KEY,
    )
    if resp.status_code != 200:
        error_msg = str(resp.message)
        if "InvalidApiKey" in error_msg or "401" in error_msg:
            raise EmbeddingAuthError(f"Embedding API 鉴权失败: {error_msg}")
        raise EmbeddingProviderError(f"Embedding API 调用失败: {error_msg}")
    # 按 input 顺序提取向量
    ordered = sorted(resp.output["embeddings"], key=lambda x: x["text_index"])
    return [item["embedding"] for item in ordered]


def _openai_embed(texts: list[str]) -> list[list[float]]:
    """OpenAI 兼容协议 embedding"""
    import requests

    api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
    if not api_key:
        raise EmbeddingAuthError("EMBEDDING_API_KEY 或 LLM_API_KEY 未配置")

    base = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL or "https://api.openai.com/v1"
    model = settings.EMBEDDING_MODEL or "text-embedding-v3"
    url = f"{base.rstrip('/')}/embeddings"

    try:
        resp = requests.post(
            url,
            json={"input": texts, "model": model},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=max(5, settings.EMBEDDING_TIMEOUT),
        )
        resp.raise_for_status()
    except requests.Timeout as e:
        raise EmbeddingTimeoutError(f"Embedding API 调用超时: {e}") from e
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if status in (401, 403):
            raise EmbeddingAuthError(f"Embedding API 鉴权失败(HTTP {status}): {e}") from e
        raise EmbeddingProviderError(f"Embedding API 调用失败(HTTP {status}): {e}") from e
    except requests.RequestException as e:
        raise EmbeddingProviderError(f"Embedding API 调用失败: {e}") from e

    data = resp.json()
    ordered = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in ordered]


def _known_embedding_dimension(model: str) -> int | None:
    """根据常见模型名返回默认维度，未知返回 None。"""
    normalized = (model or "").strip().lower()
    if normalized == "text-embedding-v3":
        return 1024
    if normalized in {"text-embedding-3-large"}:
        return 3072
    if normalized in {"text-embedding-3-small", "text-embedding-ada-002"}:
        return 1536
    return None


def validate_embedding_dimension(
    vectors: list[list[float]],
    expected_dimension: int | None = None,
) -> tuple[bool, int | None, int | None]:
    """校验向量维度是否一致并返回实际维度。

    Returns:
        (ok, expected, actual)
    """
    if not vectors:
        return True, expected_dimension, expected_dimension

    actual = len(vectors[0])
    exp = expected_dimension or _known_embedding_dimension(settings.EMBEDDING_MODEL)
    if exp is not None and actual != exp:
        return False, exp, actual
    return True, exp, actual


def get_expected_embedding_dimension(collection) -> int | None:
    """从 Chroma collection metadata 读取期望维度。"""
    try:
        metadata = collection.metadata or {}
        dim = metadata.get("embedding_dimension")
        if dim is not None:
            return int(dim)
    except Exception:
        logger.debug("Failed to read embedding_dimension from collection metadata")
    return None


def set_expected_embedding_dimension(collection, dimension: int) -> None:
    """把期望维度写入 Chroma collection metadata。"""
    try:
        collection.modify(metadata={**(collection.metadata or {}), "embedding_dimension": dimension})
    except Exception:
        logger.warning("Failed to set embedding_dimension in collection metadata", exc_info=True)


def embed_text(text: str) -> list[float]:
    """单条文本向量化"""
    return embed_texts([text])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量文本向量化。
    通过 settings.EMBEDDING_PROVIDER 切换后端。

    缓存策略：
      - 逐条查缓存，命中则直接复用，避免重复调用 embedding API
      - 未命中的文本按 _EMBED_BATCH_SIZE 分批请求，结果回写缓存
      - mock 模式不走缓存（本身无网络开销且基于 hash 确定性生成）

    网络型 provider（dashscope / qwen / openai）有单次批量上限
    （dashscope text-embedding-v3 仅允许 10 条/次），这里统一按
    _EMBED_BATCH_SIZE 分批调用，避免文档切片超过上限时整批失败。
    """
    if not texts:
        return []

    provider = (settings.EMBEDDING_PROVIDER or "mock").lower()
    model = settings.EMBEDDING_MODEL or "text-embedding-v3"

    if provider == "mock":
        _log_embedding_stats(
            provider=provider,
            model=model,
            total_texts=len(texts),
            cache_hits=0,
            cache_misses=len(texts),
            batch_count=0,
        )
        return [_mock_embed(t) for t in texts]

    # ---- 1) 查缓存，分离命中/未命中 ----
    with _EMBED_CACHE_LOCK:
        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        for i, text in enumerate(texts):
            key = _embed_cache_key(provider, text)
            cached = _EMBED_CACHE.get(key)
            if cached is not None:
                _EMBED_CACHE.move_to_end(key)  # LRU：命中刷新到最新
                results[i] = cached
            else:
                missing_indices.append(i)
                missing_texts.append(text)

    cache_hits = len(texts) - len(missing_texts)
    batch_count = 0

    # 记录缓存命中
    if cache_hits > 0:
        record_embedding_request(provider=provider, model=model, text_count=cache_hits)

    if not missing_texts:
        # 全部命中缓存
        _log_embedding_stats(
            provider=provider,
            model=model,
            total_texts=len(texts),
            cache_hits=cache_hits,
            cache_misses=0,
            batch_count=0,
        )
        return results  # type: ignore[return-value]

    # ---- 2) 对未命中的文本批量请求 embedding ----
    if provider == "dashscope":
        fn = _dashscope_embed
    elif provider in ("openai", "qwen"):
        fn = _openai_embed
    else:
        raise ValueError(f"未知的 EMBEDDING_PROVIDER: {provider}")

    fetched: list[list[float]] = []
    time.time()
    try:
        for i in range(0, len(missing_texts), _EMBED_BATCH_SIZE):
            batch = missing_texts[i : i + _EMBED_BATCH_SIZE]
            batch_count += 1
            fetched.extend(_with_retry(fn, batch))
    except EmbeddingProviderError as e:
        error_type = type(e).__name__
        record_embedding_error(provider=provider, model=model, error_type=error_type)
        raise
    except Exception as e:
        record_embedding_error(provider=provider, model=model, error_type=type(e).__name__)
        raise EmbeddingProviderError(f"Embedding 调用失败: {e}") from e
    finally:
        # 记录网络调用指标
        if missing_texts:
            record_embedding_request(provider=provider, model=model, text_count=len(missing_texts))

    # ---- 3) 回填结果并写入缓存 ----
    with _EMBED_CACHE_LOCK:
        for idx_in_missing, vec in enumerate(fetched):
            original_idx = missing_indices[idx_in_missing]
            results[original_idx] = vec
            key = _embed_cache_key(provider, missing_texts[idx_in_missing])
            _EMBED_CACHE[key] = vec
            if len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
                _EMBED_CACHE.popitem(last=False)  # 淘汰最久未用

    _log_embedding_stats(
        provider=provider,
        model=model,
        total_texts=len(texts),
        cache_hits=cache_hits,
        cache_misses=len(missing_texts),
        batch_count=batch_count,
    )

    return results  # type: ignore[return-value]
