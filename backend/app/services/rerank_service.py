# -*- coding: utf-8 -*-
"""Document-level rerank service with graceful fallback."""
import logging
import math
import os
import threading
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_RERANK_MODEL = None
_RERANK_TOKENIZER = None
_RERANK_LOAD_ERROR: Optional[str] = None
_RERANK_LOCK = threading.Lock()


def _tokenize(text: str) -> List[str]:
    try:
        import jieba
        return [item.strip().lower() for item in jieba.cut(text or "") if item.strip()]
    except ImportError:
        text = (text or "").strip().lower()
        return [text[i:i + 2] for i in range(max(0, len(text) - 1))] if text else []


def _vector_distance_to_similarity(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / (1.0 + max(value, 0.0))


def _normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _heuristic_relevance(query: str, item: Dict) -> float:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.0

    text_tokens = set(_tokenize(item.get("text", "")))
    title_tokens = set(_tokenize(item.get("doc_title", "")))

    text_overlap = len(query_tokens & text_tokens) / max(1, len(query_tokens))
    title_overlap = len(query_tokens & title_tokens) / max(1, len(query_tokens))
    recall_bonus = min(len(item.get("recalled_by", [])) / 3.0, 1.0)
    return min(1.0, text_overlap * 0.55 + title_overlap * 0.25 + recall_bonus * 0.20)


def _get_local_reranker():
    global _RERANK_MODEL, _RERANK_TOKENIZER, _RERANK_LOAD_ERROR
    if _RERANK_MODEL is not None and _RERANK_TOKENIZER is not None:
        return _RERANK_TOKENIZER, _RERANK_MODEL
    if _RERANK_LOAD_ERROR:
        return None, None

    model_path = settings.RERANKER_MODEL_PATH
    if not model_path or not os.path.exists(model_path):
        _RERANK_LOAD_ERROR = "reranker model path missing"
        return None, None

    with _RERANK_LOCK:
        if _RERANK_MODEL is not None and _RERANK_TOKENIZER is not None:
            return _RERANK_TOKENIZER, _RERANK_MODEL
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            _RERANK_TOKENIZER = AutoTokenizer.from_pretrained(model_path)
            _RERANK_MODEL = AutoModelForSequenceClassification.from_pretrained(model_path)
            _RERANK_MODEL.eval()
            logger.info("Loaded local reranker model from %s", model_path)
        except Exception as exc:
            _RERANK_LOAD_ERROR = str(exc)
            logger.warning("Load reranker model failed: %s", exc)
            return None, None
    return _RERANK_TOKENIZER, _RERANK_MODEL


def _local_rerank_scores(query: str, items: List[Dict]) -> Optional[List[float]]:
    if not items:
        return []

    tokenizer, model = _get_local_reranker()
    if tokenizer is None or model is None:
        return None

    try:
        import torch
    except Exception as exc:
        logger.warning("Torch unavailable for local reranker: %s", exc)
        return None

    scores: List[float] = []
    batch_size = max(1, settings.RERANKER_BATCH_SIZE)
    pairs = [[query, item.get("text", "")] for item in items]

    for i in range(0, len(pairs), batch_size):
        batch_pairs = pairs[i:i + batch_size]
        inputs = tokenizer(
            batch_pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(**inputs).logits.view(-1)
            batch_scores = torch.sigmoid(logits).cpu().tolist()
        scores.extend(batch_scores)
    return scores


def rerank_results(query: str, results: List[Dict], top_k: Optional[int] = None) -> List[Dict]:
    """Rerank fused candidates. Uses local cross-encoder if available, else heuristic fallback."""
    if not results:
        return []

    local_scores = None
    provider = (settings.RERANKER_PROVIDER or "auto").lower()
    if provider in {"auto", "local"}:
        local_scores = _local_rerank_scores(query, results)

    vector_scores = [_vector_distance_to_similarity(item.get("vector_score", item.get("score"))) for item in results]
    bm25_scores = [float(item.get("bm25_relevance", 0.0) or 0.0) for item in results]
    lexical_scores = [_heuristic_relevance(query, item) for item in results]

    vector_norm = _normalize(vector_scores)
    bm25_norm = _normalize(bm25_scores)

    rerank_scores = local_scores if local_scores is not None else lexical_scores
    rerank_source = "local_cross_encoder" if local_scores is not None else "heuristic"

    ranked: List[Dict] = []
    for idx, item in enumerate(results):
        final_score = vector_norm[idx] * 0.5 + bm25_norm[idx] * 0.3 + rerank_scores[idx] * 0.2
        enriched = dict(item)
        enriched["vector_similarity"] = round(vector_norm[idx], 4)
        enriched["keyword_score"] = round(bm25_norm[idx], 4)
        enriched["rerank_score"] = round(rerank_scores[idx], 4)
        enriched["rerank_source"] = rerank_source
        enriched["final_score"] = round(final_score, 4)
        ranked.append(enriched)

    ranked.sort(key=lambda item: item.get("final_score", 0.0), reverse=True)
    if top_k is not None:
        ranked = ranked[:top_k]
    return ranked
