"""Organization knowledge base isolation tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.knowledge import router as knowledge_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.knowledge import KnowledgeDocument
from app.models.organization import Organization, OrganizationMembership
from app.models.user import User


def _user(db, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("StrongP@ssw0rd"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User, organization_id: int | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'email': user.email, 'username': user.username})}"
    }
    if organization_id is not None:
        headers["X-Organization-ID"] = str(organization_id)
    return headers


def _document(*, organization_id: int | None = None, user_id: int | None = None, title: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        organization_id=organization_id,
        user_id=user_id,
        title=title,
        file_name=f"{title}.md",
        file_type="md",
        file_size=10,
        file_path=f"knowledge/{title}.md",
        doc_type="general",
        status="ready",
    )


def test_organization_knowledge_isolated_from_personal_and_other_workspaces(db_session, monkeypatch):
    app = FastAPI()
    app.include_router(knowledge_router, prefix="/knowledge")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    owner = _user(db_session, "knowledge_owner")
    member = _user(db_session, "knowledge_member")
    outsider = _user(db_session, "knowledge_outsider")
    organization = Organization(name="One", slug="knowledge-one", owner_id=owner.id)
    other_organization = Organization(name="Two", slug="knowledge-two", owner_id=outsider.id)
    db_session.add_all([organization, other_organization])
    db_session.flush()
    db_session.add_all(
        [
            OrganizationMembership(organization_id=organization.id, user_id=owner.id, role="owner"),
            OrganizationMembership(organization_id=organization.id, user_id=member.id, role="member"),
            OrganizationMembership(organization_id=other_organization.id, user_id=outsider.id, role="owner"),
        ]
    )
    docs = [
        _document(organization_id=organization.id, title="team-doc"),
        _document(organization_id=other_organization.id, title="other-team-doc"),
        _document(user_id=owner.id, title="private-doc"),
        _document(title="platform-doc"),
    ]
    db_session.add_all(docs)
    db_session.commit()
    for document in docs:
        db_session.refresh(document)

    monkeypatch.setattr(
        "app.services.rag_service.get_knowledge_collection",
        lambda: type(
            "FakeCollection",
            (),
            {
                "count": lambda self: 4,
                "query": lambda self, **kwargs: {
                    "ids": [[f"doc_{doc.id}" for doc in docs]],
                    "documents": [[doc.title for doc in docs]],
                    "metadatas": [
                        [
                            {"doc_id": str(doc.id), "doc_title": doc.title, "doc_type": "general", "chunk_index": 0}
                            for doc in docs
                        ]
                    ],
                    "distances": [[0.01, 0.02, 0.03, 0.04]],
                },
            },
        )(),
    )
    monkeypatch.setattr("app.services.rag_service.embed_text", lambda query: [0.1, 0.2, 0.3])

    with TestClient(app) as client:
        listed = client.get("/knowledge/list", headers=_headers(member, organization.id))
        assert [item["title"] for item in listed.json()["data"]["items"]] == ["team-doc"]

        searched = client.post("/knowledge/search", headers=_headers(member, organization.id), json={"query": "test", "top_k": 5})
        assert [item["doc_title"] for item in searched.json()["data"]["results"]] == ["team-doc", "platform-doc"]

        denied_detail = client.get(f"/knowledge/{docs[0].id}", headers=_headers(outsider))
        assert denied_detail.json()["code"] != 0

        denied_scope = client.get("/knowledge/list", headers=_headers(outsider, organization.id))
        assert denied_scope.json()["code"] != 0

        denied_manage = client.post(f"/knowledge/{docs[0].id}/reprocess", headers=_headers(member))
        assert denied_manage.json()["code"] != 0
