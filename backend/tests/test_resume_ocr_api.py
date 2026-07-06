# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.auth import router as auth_router
from app.api.resume import router as resume_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import Resume
from app.models.user import User


@pytest.fixture
def resume_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
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


def test_resume_upload_accepts_png_image(resume_client, db_session, monkeypatch):
    user = _create_user(db_session, "resume_png_owner", "resume_png_owner@example.com")

    def fake_save_upload_file(file_bytes, original_filename):
        assert original_filename == "resume.png"
        return {
            "file_name": original_filename,
            "file_path": "uploads/2026/06/mock_resume.png",
            "file_type": "png",
            "file_size": len(file_bytes),
        }

    monkeypatch.setattr("app.api.resume.resume_service.save_upload_file", fake_save_upload_file)

    response = resume_client.post(
        "/resume/upload",
        headers=_auth_headers(user),
        files={"file": ("resume.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["file_type"] == "png"
    saved = db_session.query(Resume).filter(Resume.user_id == user.id).all()
    assert len(saved) == 1


def test_resume_parse_returns_friendly_ocr_disabled_message(resume_client, db_session, monkeypatch):
    user = _create_user(db_session, "resume_ocr_owner", "resume_ocr_owner@example.com")
    resume = Resume(
        user_id=user.id,
        file_name="scan_resume.png",
        file_path="uploads/2026/06/scan_resume.png",
        file_type="png",
        file_size=1234,
        is_deleted=0,
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)

    def fake_parse_and_save(db, resume_id):
        raise ValueError("当前环境未开启 OCR 简历识别，请联系管理员开启后再上传图片简历或扫描件 PDF")

    monkeypatch.setattr("app.api.resume.resume_service.parse_and_save", fake_parse_and_save)

    response = resume_client.post(
        "/resume/parse",
        headers=_auth_headers(user),
        json={"resume_id": resume.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] != 0
    assert "未开启 OCR 简历识别" in body["message"]
