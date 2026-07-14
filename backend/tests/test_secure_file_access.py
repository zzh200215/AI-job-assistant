"""Tests for authenticated file access and ownership checks."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.knowledge import router as knowledge_router
from app.api.resume import router as resume_router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import Resume
from app.models.knowledge import KnowledgeDocument
from app.models.user import User


@pytest.fixture
def secure_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(knowledge_router, prefix="/knowledge")
    app.include_router(resume_router, prefix="/resume")

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


def test_knowledge_list_defaults_to_current_user(secure_client, db_session):
    owner = _create_user(db_session, "owner_user", "owner@example.com")
    other = _create_user(db_session, "other_user", "other@example.com")

    db_session.add_all(
        [
            KnowledgeDocument(
                user_id=owner.id,
                title="owner-doc",
                file_name="owner.md",
                file_type="md",
                file_size=12,
                file_path="knowledge/2026/06/owner.md",
                doc_type="general",
                status="ready",
            ),
            KnowledgeDocument(
                user_id=other.id,
                title="other-doc",
                file_name="other.md",
                file_type="md",
                file_size=12,
                file_path="knowledge/2026/06/other.md",
                doc_type="general",
                status="ready",
            ),
        ]
    )
    db_session.commit()

    response = secure_client.get("/knowledge/list", headers=_auth_headers(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert [item["title"] for item in body["data"]["items"]] == ["owner-doc"]


def test_knowledge_detail_blocks_other_user_and_allows_admin(secure_client, db_session):
    admin = _create_user(db_session, "admin", "admin@example.com")
    owner = _create_user(db_session, "doc_owner", "doc_owner@example.com")

    doc = KnowledgeDocument(
        user_id=owner.id,
        title="secret-doc",
        file_name="secret.md",
        file_type="md",
        file_size=12,
        file_path="knowledge/2026/06/secret.md",
        doc_type="general",
        status="ready",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    outsider = _create_user(db_session, "outsider", "outsider@example.com")
    denied = secure_client.get(f"/knowledge/{doc.id}", headers=_auth_headers(outsider))
    assert denied.json()["code"] != 0

    allowed = secure_client.get(f"/knowledge/{doc.id}", headers=_auth_headers(admin))
    assert allowed.status_code == 200
    assert allowed.json()["code"] == 0
    assert allowed.json()["data"]["title"] == "secret-doc"


def test_knowledge_download_streams_with_owner_check(secure_client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    owner = _create_user(db_session, "download_owner", "download_owner@example.com")
    outsider = _create_user(db_session, "download_other", "download_other@example.com")

    file_path = Path(settings.UPLOAD_DIR) / "knowledge" / "2026" / "06" / "kb.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"knowledge-body")

    doc = KnowledgeDocument(
        user_id=owner.id,
        title="download-doc",
        file_name="kb.md",
        file_type="md",
        file_size=file_path.stat().st_size,
        file_path="knowledge/2026/06/kb.md",
        doc_type="general",
        status="ready",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    denied = secure_client.get(f"/knowledge/{doc.id}/download", headers=_auth_headers(outsider))
    assert denied.json()["code"] != 0

    allowed = secure_client.get(f"/knowledge/{doc.id}/download", headers=_auth_headers(owner))
    assert allowed.status_code == 200
    assert allowed.content == b"knowledge-body"
    assert "attachment" in allowed.headers["content-disposition"].lower()


def test_resume_download_streams_with_auth(secure_client, db_session, tmp_path, monkeypatch, mocker):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    owner = _create_user(db_session, "resume_owner", "resume_owner@example.com")
    outsider = _create_user(db_session, "resume_other", "resume_other@example.com")

    export_path = Path(settings.UPLOAD_DIR) / "export" / "2026" / "06" / "resume.docx"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_bytes(b"resume-bytes")

    resume = Resume(
        user_id=owner.id,
        file_name="resume.docx",
        file_path="uploads/2026/06/source.docx",
        file_type="docx",
        file_size=123,
        optimized_content="optimized",
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)

    mocker.patch(
        "app.api.resume.resume_export_service.export_docx",
        return_value="uploads/export/2026/06/resume.docx",
    )

    denied = secure_client.get(
        f"/resume/{resume.id}/download",
        params={"format": "docx", "version": "optimized"},
        headers=_auth_headers(outsider),
    )
    assert denied.json()["code"] != 0

    allowed = secure_client.get(
        f"/resume/{resume.id}/download",
        params={"format": "docx", "version": "optimized"},
        headers=_auth_headers(owner),
    )
    assert allowed.status_code == 200
    assert allowed.content == b"resume-bytes"
    assert "attachment" in allowed.headers["content-disposition"].lower()
