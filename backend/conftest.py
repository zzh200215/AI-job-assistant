"""Pytest bootstrap for backend tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Unit tests must not inherit external services configured in the developer's .env.
os.environ["TESTING"] = "true"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["ORCHESTRATION_BACKEND"] = "thread"
os.environ["RUN_SCHEDULER"] = "false"
# 必须在导入 app.core.database（settings 单例实例化）之前设置，否则 settings 会绑定到
# 开发者 .env 的 MySQL，导致后台任务（SessionLocal）连到真实数据库（tests/conftest 中再设已太晚）。
# database.py 已为内存 sqlite 启用 StaticPool，此处建表后所有连接共享同一库。
os.environ["DATABASE_URL"] = "sqlite://"

# 注册全部模型并给 app 引擎建表，使后台任务（SessionLocal 直连 app 引擎）可查询。
import app.models  # noqa: F401
from app.core.database import Base, SessionLocal
from app.core.database import engine as _app_engine

Base.metadata.create_all(bind=_app_engine)

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@compiles(BigInteger, "sqlite")
def _compile_big_integer_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


# ===================== Database Fixtures =====================


@pytest.fixture
def mocker():
    """Small pytest-mock compatible subset used by this suite."""
    patchers = []

    class Mocker:
        MagicMock = mock.MagicMock

        def patch(self, target: str, *args, **kwargs):
            patcher = mock.patch(target, *args, **kwargs)
            patched = patcher.start()
            patchers.append(patcher)
            return patched

    yield Mocker()

    for patcher in reversed(patchers):
        patcher.stop()


@pytest.fixture
def db_session() -> Session:
    """In-memory SQLite session with all tables created."""
    # Ensure all models are imported so their tables register in Base.metadata
    import app.models.agent  # noqa: F401
    import app.models.agent_run  # noqa: F401
    import app.models.embedding_usage  # noqa: F401
    import app.models.history  # noqa: F401
    import app.models.interview_session  # noqa: F401
    import app.models.job_pipeline  # noqa: F401
    import app.models.job_recommend  # noqa: F401
    import app.models.knowledge  # noqa: F401
    import app.models.prompt_trace  # noqa: F401
    import app.models.user  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Use sorted_tables to respect ForeignKey dependency order
    Base.metadata.create_all(
        bind=engine,
        tables=Base.metadata.sorted_tables,
    )
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    from app.services.embedding_service import set_embedding_stats_session_factory

    set_embedding_stats_session_factory(lambda: session)
    try:
        yield session
    finally:
        set_embedding_stats_session_factory(SessionLocal)
        session.close()


@pytest.fixture
def db_session_with_tables(db_session: Session) -> Session:
    """Alias for db_session — all tables already created by Base.metadata."""
    return db_session


# ===================== Data Builders =====================


@pytest.fixture
def make_resume(db_session: Session):
    """Factory fixture: create a Resume record and return it."""
    created = []

    def _make(
        name: str = "测试用户",
        file_name: str = "resume.pdf",
        parsed_json: dict | None = None,
        **overrides,
    ) -> int:
        from app.models.history import Resume

        obj = Resume(
            name=name,
            file_name=file_name,
            file_path=f"uploads/{file_name}",
            file_type="pdf",
            file_size=1024,
            parsed_json=parsed_json
            or {
                "name": name,
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "years_exp": 3,
                "current_title": "后端工程师",
                "education": "本科",
                "self_evaluation": "3年后端开发经验",
                "work_experience": [],
                "project_experience": [],
            },
            **overrides,
        )
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        created.append(obj)
        return obj.id

    yield _make
    # cleanup not needed — db_session rollback handles it


@pytest.fixture
def make_jd(db_session: Session):
    """Factory fixture: create a JobDescription record and return its id."""

    def _make(
        title: str = "AI应用开发工程师",
        company: str = "测试科技",
        parsed_json: dict | None = None,
        **overrides,
    ) -> int:
        from app.models.history import JobDescription

        obj = JobDescription(
            title=title,
            company=company,
            raw_text=f"招聘{title}岗位",
            parsed_json=parsed_json
            or {
                "title": title,
                "company": company,
                "required_skills": ["Python", "FastAPI", "LLM"],
                "keywords": ["AI", "RAG", "Agent"],
                "responsibilities_summary": "负责AI应用开发",
            },
            **overrides,
        )
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        return obj.id

    yield _make


@pytest.fixture
def make_agent_task(db_session: Session):
    """Factory fixture: create an AgentTask record."""

    def _make(
        resume_id: int,
        jd_id: int,
        user_id: int = 1,
        status: str = "pending",
        **overrides,
    ) -> int:
        from app.models.agent import AgentTask

        obj = AgentTask(
            user_id=user_id,
            resume_id=resume_id,
            jd_id=jd_id,
            status=status,
            **overrides,
        )
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        return obj.id

    yield _make


@pytest.fixture
def make_interview_session(db_session: Session):
    """Factory fixture: create an InterviewSession record."""

    def _make(
        user_id: int = 1,
        resume_id: int = 1,
        jd_id: int = 1,
        status: str = "created",
        questions: list[dict] | None = None,
        **overrides,
    ) -> int:
        from app.models.interview_session import InterviewSession

        obj = InterviewSession(
            user_id=user_id,
            resume_id=resume_id,
            jd_id=jd_id,
            interview_type="tech",
            status=status,
            questions=questions
            if questions is not None
            else [
                {
                    "id": 0,
                    "question": "请介绍你的项目经验",
                    "category": "project",
                    "ref_answer": "从背景、挑战、方案、成果四方面回答",
                },
                {"id": 1, "question": "解释RAG的工作原理", "category": "tech", "ref_answer": "检索+生成两阶段"},
                {"id": 2, "question": "如何处理高并发请求", "category": "tech", "ref_answer": "缓存、异步、水平扩展"},
            ],
            **overrides,
        )
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        return obj.id

    yield _make


# ===================== Mock Helpers =====================


@pytest.fixture
def mock_chroma_collection(mocker):
    """Mock Chroma collection to avoid real DB dependency.

    Patches at the source AND at every module-level import site
    so all service modules use the mock instead of the real persistent client.

    Usage:
        mock_col = mock_chroma_collection
        mock_col.query.return_value = {...}
    """
    mock_col = mocker.MagicMock()
    mock_col.count.return_value = 0

    # Patch at the source
    mocker.patch("app.core.chroma_client.get_knowledge_collection", return_value=mock_col)

    # Patch at module-level import references (python imports are bound at import time)
    mocker.patch("app.services.rag_service.get_knowledge_collection", return_value=mock_col)
    mocker.patch("app.services.multi_recall.get_knowledge_collection", return_value=mock_col)

    return mock_col


@pytest.fixture
def mock_embedding(mocker):
    """Mock embedding service to return deterministic vectors."""
    mock_fn = mocker.MagicMock()
    # Return a simple fixed vector for any input
    mock_fn.side_effect = lambda text: [0.1] * 512
    mocker.patch("app.services.embedding_service.embed_text", side_effect=mock_fn)
    mocker.patch("app.services.embedding_service.embed_texts", return_value=[[0.1] * 512])
    return mock_fn


@pytest.fixture
def mock_reranker(mocker):
    """Mock rerank service to pass through results unchanged."""

    def _passthrough(query, results, top_k=None):
        if not results:
            return []
        ranked = []
        for _idx, item in enumerate(results):
            enriched = dict(item)
            enriched["vector_similarity"] = 0.5
            enriched["keyword_score"] = 0.3
            enriched["rerank_score"] = 0.5
            enriched["rerank_source"] = "heuristic"
            enriched["final_score"] = 0.5
            ranked.append(enriched)
        ranked.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        if top_k:
            ranked = ranked[:top_k]
        return ranked

    mocker.patch("app.services.rerank_service.rerank_results", side_effect=_passthrough)
    return _passthrough
