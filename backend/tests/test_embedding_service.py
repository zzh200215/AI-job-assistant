import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.models.embedding_usage import EmbeddingUsageDaily
from app.services.embedding_service import (
    clear_embed_cache,
    embed_texts,
    get_embedding_daily_stats,
    get_embedding_stats,
    reset_embedding_stats,
)


def _fake_dashscope_response(vectors):
    return SimpleNamespace(
        status_code=200,
        message="ok",
        output={"embeddings": [{"text_index": idx, "embedding": vector} for idx, vector in enumerate(vectors)]},
    )


def _fake_dashscope_module(responses):
    call_mock = MagicMock(side_effect=responses)
    module = SimpleNamespace(TextEmbedding=SimpleNamespace(call=call_mock))
    return module, call_mock


def test_dashscope_uses_configured_model_and_logs_stats(caplog):
    clear_embed_cache()
    reset_embedding_stats()
    fake_module, call_mock = _fake_dashscope_module([_fake_dashscope_response([[0.1, 0.2], [0.3, 0.4]])])
    with (
        patch.object(settings, "EMBEDDING_PROVIDER", "dashscope"),
        patch.object(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
        patch.object(settings, "EMBEDDING_API_KEY", "key"),
        patch.object(settings, "LLM_API_KEY", "llm"),
        patch.dict(sys.modules, {"dashscope": fake_module}),
        caplog.at_level("INFO"),
    ):
        vectors = embed_texts(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert call_mock.call_args.kwargs["model"] == "text-embedding-v3"
    assert "Embedding stats" in caplog.text


def test_embedding_cache_reuses_results_without_requery():
    clear_embed_cache()
    reset_embedding_stats()
    fake_module, call_mock = _fake_dashscope_module([_fake_dashscope_response([[0.1, 0.2]])])
    with (
        patch.object(settings, "EMBEDDING_PROVIDER", "dashscope"),
        patch.object(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
        patch.object(settings, "EMBEDDING_API_KEY", "key"),
        patch.object(settings, "LLM_API_KEY", "llm"),
        patch.dict(sys.modules, {"dashscope": fake_module}),
    ):
        first = embed_texts(["repeat"])
        second = embed_texts(["repeat"])

    assert first == second == [[0.1, 0.2]]
    assert call_mock.call_count == 1


def test_batching_splits_large_requests():
    clear_embed_cache()
    reset_embedding_stats()
    vectors = [[float(i), float(i + 1)] for i in range(12)]
    fake_module, call_mock = _fake_dashscope_module(
        [
            _fake_dashscope_response(vectors[:10]),
            _fake_dashscope_response(vectors[10:]),
        ]
    )

    with (
        patch.object(settings, "EMBEDDING_PROVIDER", "dashscope"),
        patch.object(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
        patch.object(settings, "EMBEDDING_API_KEY", "key"),
        patch.object(settings, "LLM_API_KEY", "llm"),
        patch.dict(sys.modules, {"dashscope": fake_module}),
    ):
        result = embed_texts([f"t{i}" for i in range(12)])

    assert result == vectors
    assert call_mock.call_count == 2


def test_runtime_stats_aggregate_calls():
    clear_embed_cache()
    reset_embedding_stats()
    fake_module, _ = _fake_dashscope_module(
        [
            _fake_dashscope_response([[0.1, 0.2], [0.3, 0.4]]),
        ]
    )

    with (
        patch.object(settings, "EMBEDDING_PROVIDER", "dashscope"),
        patch.object(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
        patch.object(settings, "EMBEDDING_API_KEY", "key"),
        patch.object(settings, "LLM_API_KEY", "llm"),
        patch.dict(sys.modules, {"dashscope": fake_module}),
    ):
        embed_texts(["same", "other"])
        embed_texts(["same"])

    stats = get_embedding_stats()
    assert stats["total_calls"] == 2
    assert stats["total_texts"] == 3
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 2
    assert stats["network_batches"] == 1
    assert stats["provider_totals"]["dashscope"] == 3
    assert stats["model_totals"]["text-embedding-v3"] == 3


def test_daily_stats_persist_to_database(db_session):
    clear_embed_cache()
    reset_embedding_stats()
    fake_module, _ = _fake_dashscope_module(
        [
            _fake_dashscope_response([[0.1, 0.2], [0.3, 0.4]]),
        ]
    )

    with (
        patch.object(settings, "EMBEDDING_PROVIDER", "dashscope"),
        patch.object(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
        patch.object(settings, "EMBEDDING_API_KEY", "key"),
        patch.object(settings, "LLM_API_KEY", "llm"),
        patch.dict(sys.modules, {"dashscope": fake_module}),
    ):
        embed_texts(["daily-a", "daily-b"])

    row = db_session.query(EmbeddingUsageDaily).one()
    assert row.provider == "dashscope"
    assert row.model == "text-embedding-v3"
    assert row.total_calls == 1
    assert row.total_texts == 2
    assert row.cache_hits == 0
    assert row.cache_misses == 2
    assert row.network_batches == 1

    trend = get_embedding_daily_stats(days=7)
    assert len(trend) == 1
    assert trend[0]["provider"] == "dashscope"


def test_mock_embedding_matches_text_embedding_v3_dimension():
    clear_embed_cache()
    reset_embedding_stats()

    with (
        patch.object(settings, "EMBEDDING_PROVIDER", "mock"),
        patch.object(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
    ):
        vectors = embed_texts(["dimension-check"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 1024
