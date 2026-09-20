"""B3: job embeddings that survive a restart, and an honest record of when the
vector channel is unavailable.

`recommend()` used to embed the entire active-JD table on every uncached call,
with nothing but a 512-entry in-process LRU between calls: a restart re-paid the
whole cost, and the corpus grows linearly in API batches. Vectors now live in
`jd_embedding`, keyed by (jd, provider, model) plus the fingerprint of the text
they were computed from, so only new or edited postings are ever re-embedded.

Nothing here pretends a missing vector is a mid-range score. When the provider
fails, the affected postings come back without a vector and the caller falls back
to the rule channel explicitly — the old behaviour returned 50.0, which is
indistinguishable from "average fit" and quietly reorders every recommendation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.jd_embedding import JobEmbedding
from app.services.embedding_service import embed_texts

logger = logging.getLogger(__name__)

# Texts per provider call. The embedding layer itself splits at 10; this only
# bounds how many rows one sync round holds in memory.
SYNC_CHUNK = 30
RAWS_TEXT_LIMIT = 6000


@dataclass
class EmbeddingStats:
    """What a single call had to do, so callers can report it instead of guessing."""

    scanned: int = 0
    reused: int = 0
    embedded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "reused": self.reused,
            "embedded": self.embedded,
            "failed": self.failed,
        }


def current_provider_model() -> tuple[str, str]:
    return ((settings.EMBEDDING_PROVIDER or "mock").lower(), settings.EMBEDDING_MODEL or "text-embedding-v3")


def retrieval_text(jd: Any) -> str:
    """The single text a posting is embedded from.

    Lives here rather than in the engine so the stored fingerprint and the query
    text cannot drift apart. `raw_text` is what the recruiter published, so it
    wins; the structured digest is the fallback for rows imported without it.
    """
    raw = (getattr(jd, "raw_text", "") or "").strip()
    if raw:
        return raw[:RAWS_TEXT_LIMIT]

    data = getattr(jd, "parsed_json", None) or {}
    parts: list[str] = [str(data.get("title") or getattr(jd, "title", "") or "")]
    if getattr(jd, "company", None):
        parts.append(str(jd.company))
    for key in ("required_skills", "nice_to_have", "responsibilities", "keywords"):
        value = data.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, str | int | float))
    return " ".join(part for part in parts if part)[:RAWS_TEXT_LIMIT]


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def vectors_for_jobs(db: Session, jobs: Iterable[Any]) -> tuple[dict[int, list[float]], EmbeddingStats]:
    """Return {jd_id: vector}, embedding only what is missing or stale."""
    stats = EmbeddingStats()
    provider, model = current_provider_model()
    wanted: dict[int, str] = {}
    for jd in jobs:
        if jd.id is None:
            continue
        wanted[jd.id] = retrieval_text(jd)
    stats.scanned = len(wanted)
    if not wanted:
        return {}, stats

    stored = (
        db.query(JobEmbedding)
        .filter(
            JobEmbedding.jd_id.in_(list(wanted)),
            JobEmbedding.provider == provider,
            JobEmbedding.model == model,
        )
        .all()
    )
    rows: dict[int, JobEmbedding] = {row.jd_id: row for row in stored}

    vectors: dict[int, list[float]] = {}
    stale: list[int] = []
    for jd_id, text in wanted.items():
        row = rows.get(jd_id)
        if row is not None and row.text_hash == text_fingerprint(text):
            try:
                vectors[jd_id] = json.loads(row.vector)
                stats.reused += 1
                continue
            except (ValueError, TypeError):
                logger.warning("stored embedding for jd=%s is unreadable, re-embedding", jd_id)
        stale.append(jd_id)

    if not stale:
        return vectors, stats

    for start in range(0, len(stale), SYNC_CHUNK):
        chunk = stale[start : start + SYNC_CHUNK]
        texts = [wanted[jd_id] for jd_id in chunk]
        try:
            fresh = embed_texts(texts)
        except Exception as exc:
            stats.failed += len(chunk)
            stats.errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
            logger.warning("embedding failed for %d postings, vector channel degraded: %s", len(chunk), exc)
            continue

        for jd_id, vector in zip(chunk, fresh, strict=False):
            vectors[jd_id] = vector
            stats.embedded += 1
            _store(db, jd_id, wanted[jd_id], vector, provider, model, rows.get(jd_id))
        db.commit()

    return vectors, stats


def _store(
    db: Session,
    jd_id: int,
    text: str,
    vector: list[float],
    provider: str,
    model: str,
    existing: JobEmbedding | None,
) -> None:
    row = existing or JobEmbedding(jd_id=jd_id, provider=provider, model=model)
    row.text_hash = text_fingerprint(text)
    row.dimension = len(vector)
    row.vector = json.dumps(vector)
    db.add(row)


def sync_active_job_embeddings(db: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Pre-embed the active corpus so a candidate's first request is not the one
    that pays for it. Called by the scheduler and after bulk imports."""
    from app.models.history import JobDescription

    query = db.query(JobDescription).filter(JobDescription.is_active == 1).order_by(JobDescription.id.asc())
    if limit:
        query = query.limit(limit)
    _, stats = vectors_for_jobs(db, query.all())
    return stats.to_dict()


def drop_vectors_for_jobs(db: Session, jd_ids: list[int]) -> int:
    """Used when a posting is deleted or its text changes and the row must go."""
    if not jd_ids:
        return 0
    return db.query(JobEmbedding).filter(JobEmbedding.jd_id.in_(jd_ids)).delete(synchronize_session=False)
