import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.knowledge import router as knowledge_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.knowledge import KnowledgeDocument
from app.models.user import User


@pytest.fixture
def knowledge_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(knowledge_router, prefix="/knowledge")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def test_knowledge_search_only_returns_visible_docs(knowledge_client, db_session, monkeypatch):
    owner = _create_user(db_session, "kb_owner", "kb_owner@example.com")
    other = _create_user(db_session, "kb_other", "kb_other@example.com")

    owner_doc = KnowledgeDocument(
        user_id=owner.id,
        title="owner-doc",
        file_name="owner.md",
        file_type="md",
        file_size=10,
        file_path="knowledge/2026/06/owner.md",
        doc_type="general",
        status="ready",
    )
    public_doc = KnowledgeDocument(
        user_id=None,
        title="public-doc",
        file_name="public.md",
        file_type="md",
        file_size=10,
        file_path="knowledge/2026/06/public.md",
        doc_type="general",
        status="ready",
    )
    foreign_doc = KnowledgeDocument(
        user_id=other.id,
        title="foreign-doc",
        file_name="foreign.md",
        file_type="md",
        file_size=10,
        file_path="knowledge/2026/06/foreign.md",
        doc_type="general",
        status="ready",
    )
    db_session.add_all([owner_doc, public_doc, foreign_doc])
    db_session.commit()
    db_session.refresh(owner_doc)
    db_session.refresh(public_doc)
    db_session.refresh(foreign_doc)

    monkeypatch.setattr(
        "app.services.rag_service.get_knowledge_collection",
        lambda: type(
            "FakeCollection",
            (),
            {
                "count": lambda self: 3,
                "query": lambda self, **kwargs: {
                    "ids": [[f"doc_{foreign_doc.id}", f"doc_{owner_doc.id}", f"doc_{public_doc.id}"]],
                    "documents": [["foreign text", "owner text", "public text"]],
                    "metadatas": [
                        [
                            {
                                "doc_id": str(foreign_doc.id),
                                "doc_title": foreign_doc.title,
                                "doc_type": "general",
                                "chunk_index": 0,
                            },
                            {
                                "doc_id": str(owner_doc.id),
                                "doc_title": owner_doc.title,
                                "doc_type": "general",
                                "chunk_index": 0,
                            },
                            {
                                "doc_id": str(public_doc.id),
                                "doc_title": public_doc.title,
                                "doc_type": "general",
                                "chunk_index": 0,
                            },
                        ]
                    ],
                    "distances": [[0.01, 0.02, 0.03]],
                },
            },
        )(),
    )
    monkeypatch.setattr("app.services.rag_service.embed_text", lambda query: [0.1, 0.2, 0.3])

    response = knowledge_client.post(
        "/knowledge/search",
        headers=_auth_headers(owner),
        json={"query": "test", "top_k": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    titles = [item["doc_title"] for item in body["data"]["results"]]
    assert titles == ["owner-doc", "public-doc"]
    assert "foreign-doc" not in titles


def test_analysis_references_only_return_visible_docs(knowledge_client, db_session, monkeypatch):
    owner = _create_user(db_session, "analysis_owner", "analysis_owner@example.com")
    other = _create_user(db_session, "analysis_other", "analysis_other@example.com")

    resume = Resume(
        user_id=owner.id,
        file_name="resume.pdf",
        file_path="uploads/resume.pdf",
        file_type="pdf",
        file_size=123,
        is_deleted=0,
        parsed_json={"skills": ["python"]},
    )
    jd = JobDescription(
        user_id=None,
        title="Python 后端",
        company="Public Co",
        location="Beijing",
        salary_range="20k-30k",
        raw_text="Public JD",
        parsed_json={"title": "Python 后端", "required_skills": ["python"], "keywords": ["fastapi"]},
        source="api",
        industry="AI",
        is_active=1,
    )
    db_session.add_all([resume, jd])
    db_session.commit()
    db_session.refresh(resume)
    db_session.refresh(jd)

    record = AnalysisRecord(
        user_id=owner.id,
        resume_id=resume.id,
        jd_id=jd.id,
        match_score=85,
        match_report={},
        optimize_suggestions={},
        interview_questions={},
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    owner_doc = KnowledgeDocument(
        user_id=owner.id,
        title="owner-doc",
        file_name="owner.md",
        file_type="md",
        file_size=10,
        file_path="knowledge/2026/06/owner.md",
        doc_type="general",
        status="ready",
    )
    public_doc = KnowledgeDocument(
        user_id=None,
        title="public-doc",
        file_name="public.md",
        file_type="md",
        file_size=10,
        file_path="knowledge/2026/06/public.md",
        doc_type="general",
        status="ready",
    )
    foreign_doc = KnowledgeDocument(
        user_id=other.id,
        title="foreign-doc",
        file_name="foreign.md",
        file_type="md",
        file_size=10,
        file_path="knowledge/2026/06/foreign.md",
        doc_type="general",
        status="ready",
    )
    db_session.add_all([owner_doc, public_doc, foreign_doc])
    db_session.commit()
    db_session.refresh(owner_doc)
    db_session.refresh(public_doc)
    db_session.refresh(foreign_doc)

    monkeypatch.setattr(
        "app.services.rag_service.get_knowledge_collection",
        lambda: type(
            "FakeCollection",
            (),
            {
                "count": lambda self: 3,
                "query": lambda self, **kwargs: {
                    "ids": [[f"doc_{foreign_doc.id}", f"doc_{owner_doc.id}", f"doc_{public_doc.id}"]],
                    "documents": [["foreign text", "owner text", "public text"]],
                    "metadatas": [
                        [
                            {
                                "doc_id": str(foreign_doc.id),
                                "doc_title": foreign_doc.title,
                                "doc_type": "general",
                                "chunk_index": 0,
                            },
                            {
                                "doc_id": str(owner_doc.id),
                                "doc_title": owner_doc.title,
                                "doc_type": "general",
                                "chunk_index": 0,
                            },
                            {
                                "doc_id": str(public_doc.id),
                                "doc_title": public_doc.title,
                                "doc_type": "general",
                                "chunk_index": 0,
                            },
                        ]
                    ],
                    "distances": [[0.01, 0.02, 0.03]],
                },
            },
        )(),
    )
    monkeypatch.setattr("app.services.rag_service.embed_text", lambda query: [0.1, 0.2, 0.3])

    analysis_app = FastAPI()
    from app.api.analysis import router as analysis_router

    analysis_app.include_router(auth_router, prefix="/auth")
    analysis_app.include_router(analysis_router, prefix="/analysis")

    def override_get_db():
        yield db_session

    analysis_app.dependency_overrides[get_db] = override_get_db

    with TestClient(analysis_app) as client:
        response = client.get(f"/analysis/{record.id}/references", headers=_auth_headers(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    titles = [item["doc_title"] for item in body["data"]["references"]]
    assert titles == ["owner-doc", "public-doc"]
    assert "foreign-doc" not in titles
