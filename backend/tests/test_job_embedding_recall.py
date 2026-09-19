"""B3: embeddings are paid for once, and an outage is visible rather than averaged in.

Before this, every uncached recommendation embedded the whole active-JD table and
a failed embedding silently became a vector score of 50.0 — a third of the
blend, indistinguishable from a genuinely average semantic match.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.jd_embedding import JobEmbedding
from app.models.history import JobDescription
from app.services import jd_embedding_service
from app.services.job_recommend_engine import JobRecommendationEngine
from app.services.jd_embedding_service import (
    current_provider_model,
    retrieval_text,
    sync_active_job_embeddings,
    text_fingerprint,
    vectors_for_jobs,
)


@pytest.fixture(autouse=True)
def clear_recommend_cache():
    JobRecommendationEngine.clear_cache()
    yield
    JobRecommendationEngine.clear_cache()


def _job(db, title, *, company="Test Co", raw_text=None, required=None):
    job = JobDescription(
        title=title,
        company=company,
        location="Beijing",
        salary_range="25k-35k",
        raw_text=raw_text if raw_text is not None else f"{title} role needs python",
        industry="AI",
        is_active=1,
        experience_requirement="3-5 years",
        parsed_json={"title": title, "required_skills": required or ["python", "fastapi"]},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@pytest.fixture
def resume_id(make_resume):
    return make_resume(
        parsed_json={
            "name": "张三",
            "skills": ["Python", "FastAPI"],
            "years_exp": 3,
            "education": "本科",
            "self_evaluation": "后端开发",
        }
    )


class EmbedRecorder:
    """Stands in for the provider: hands out a distinct vector per text."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("provider down")
        return [[1.0, float(i % 7) / 10] for i in range(len(texts))]


# ---------------------------------------------------------------- cost


def test_the_corpus_is_embedded_once_not_once_per_request(db_session, monkeypatch, resume_id):
    for i in range(3):
        _job(db_session, f"岗位{i}")

    recorder = EmbedRecorder()
    monkeypatch.setattr(jd_embedding_service, "embed_texts", recorder)
    engine = JobRecommendationEngine(db_session)

    engine.recommend(resume_id=resume_id, limit=5, bypass_cache=True)
    assert len(recorder.calls) == 1, "整个岗位库一次批量嵌入"

    engine.recommend(resume_id=resume_id, limit=5, bypass_cache=True)
    assert len(recorder.calls) == 1, "第二次请求不应再嵌岗位库"


def test_editing_one_posting_reembeds_only_that_posting(db_session, monkeypatch, resume_id):
    a = _job(db_session, "岗位A")
    _job(db_session, "岗位B")
    recorder = EmbedRecorder()
    monkeypatch.setattr(jd_embedding_service, "embed_texts", recorder)

    sync_active_job_embeddings(db_session)
    recorder.calls.clear()

    a.raw_text = "岗位A 改过了，需要 Rust"
    db_session.add(a)
    db_session.commit()

    stats = sync_active_job_embeddings(db_session)

    assert stats["embedded"] == 1
    assert stats["reused"] == 1
    assert recorder.calls == [["岗位A 改过了，需要 Rust"]]


def test_clearing_the_process_cache_does_not_re_embed_the_corpus(db_session, monkeypatch, resume_id):
    """Stand-in for a restart: the in-process embedding LRU is emptied, and the
    persisted rows — not the provider — are what the next request reads."""
    from app.services.embedding_service import clear_embed_cache

    _job(db_session, "岗位A")
    recorder = EmbedRecorder()
    monkeypatch.setattr(jd_embedding_service, "embed_texts", recorder)
    sync_active_job_embeddings(db_session)
    recorder.calls.clear()

    clear_embed_cache()
    stats = sync_active_job_embeddings(db_session)

    assert recorder.calls == []
    assert stats["reused"] == 1 and stats["embedded"] == 0


def test_a_vector_from_another_model_is_not_reused(db_session, monkeypatch, resume_id):
    job = _job(db_session, "岗位A")
    provider, model = current_provider_model()
    db_session.add(
        JobEmbedding(
            jd_id=job.id,
            provider=provider,
            model="some-other-embedding-model",
            text_hash=text_fingerprint(retrieval_text(job)),
            dimension=2,
            vector="[1.0, 1.0]",
        )
    )
    db_session.commit()

    recorder = EmbedRecorder()
    monkeypatch.setattr(jd_embedding_service, "embed_texts", recorder)
    vectors, stats = vectors_for_jobs(db_session, [job])

    assert stats.embedded == 1
    assert job.id in vectors


# ---------------------------------------------------------------- degradation


def test_an_embedding_outage_falls_back_to_rules_without_a_fake_50(
    db_session, monkeypatch, resume_id
):
    from app.services import job_recommend_engine as engine_mod

    _job(db_session, "岗位A", company="甲公司")
    _job(db_session, "岗位B", company="乙公司")
    broken = EmbedRecorder(fail=True)
    monkeypatch.setattr(jd_embedding_service, "embed_texts", broken)
    monkeypatch.setattr(engine_mod, "embed_texts", broken)
    seen = []
    monkeypatch.setattr(engine_mod, "record_recommend_vector_degraded", lambda reason: seen.append(reason))

    rows = JobRecommendationEngine(db_session).recommend(resume_id=resume_id, limit=5, bypass_cache=True)

    assert rows, "向量通道不可用时仍应给出规则排序的结果"
    assert {row["retrieval_basis"] for row in rows} == {"rule_only"}
    assert all(row["vector_score"] is None for row in rows), "缺失的向量不能伪装成 50 分"
    assert all(row["retrieval_score"] == pytest.approx(row["rule_score"]) for row in rows)
    assert "posting_vectors_missing" in seen


def test_a_working_vector_channel_is_labelled_as_such(db_session, monkeypatch, resume_id):
    from app.services import job_recommend_engine as engine_mod

    _job(db_session, "岗位A")
    monkeypatch.setattr(jd_embedding_service, "embed_texts", EmbedRecorder())
    monkeypatch.setattr(engine_mod, "embed_texts", lambda texts: [[1.0, 0.5] for _ in texts])

    rows = JobRecommendationEngine(db_session).recommend(resume_id=resume_id, limit=5, bypass_cache=True)

    assert {row["retrieval_basis"] for row in rows} == {"vector+rule"}


# ---------------------------------------------------------------- diversity


def test_one_employer_cannot_fill_the_recommended_page(db_session, monkeypatch, resume_id):
    from app.services import job_recommend_engine as engine_mod
    from app.services import match_score_service

    monkeypatch.setattr(jd_embedding_service, "embed_texts", EmbedRecorder())
    monkeypatch.setattr(engine_mod, "embed_texts", lambda texts: [[1.0, 0.5] for _ in texts])
    # Same score for every posting, so only company can break the tie.
    monkeypatch.setattr(match_score_service, "compute_canonical_score", lambda resume, jd: {
        "score": 70.0, "raw_score": 70.0, "cap_applied": None, "method": "test",
        "dimensions": [], "skill_gap": [],
    })
    jobs = [_job(db_session, f"大厂岗位{i}", company="同一家") for i in range(5)]
    others = [_job(db_session, f"其他岗位{i}", company=f"公司{i}") for i in range(3)]

    rows = JobRecommendationEngine(db_session).recommend(resume_id=resume_id, limit=4, bypass_cache=True)

    assert len(rows) == 4
    from collections import Counter

    companies = Counter(row["company"] for row in rows)
    assert companies["同一家"] <= 2, "同一家公司最多占两个可见名额"
    assert companies["公司0"] == 1 and companies["公司1"] == 1
    assert {row["jd_id"] for row in rows} <= {j.id for j in jobs + others}


def test_spilling_does_not_drop_any_candidate():
    from app.services.job_recommend_engine import RecommendResult, JobRecommendationEngine

    def result(company, score):
        return RecommendResult(
            jd_id=hash(company) % 1000 + score,
            job_title="t",
            company=company,
            location="上海",
            salary_range="",
            industry="",
            match_score=score,
            vector_score=None,
            rule_score=score,
        )

    rows = [result("同一家", 1), result("同一家", 2), result("同一家", 3), result("另一家", 0)]
    spread = JobRecommendationEngine._spread_by_company(rows)

    assert len(spread) == len(rows)
    assert [r.company for r in spread] == ["同一家", "同一家", "另一家", "同一家"]


# ---------------------------------------------------------------- text choice


def test_retrieval_text_prefers_the_published_body(db_session):
    job = _job(db_session, "岗位A", raw_text="原始 JD 全文")
    assert retrieval_text(job) == "原始 JD 全文"

    job.raw_text = ""
    assert "岗位A" in retrieval_text(job)
    assert "python" in retrieval_text(job)


def test_fingerprint_tracks_text_only():
    assert text_fingerprint("同一句") == text_fingerprint("同一句")
    assert text_fingerprint("同一句") != text_fingerprint("同一句改了一个字")
