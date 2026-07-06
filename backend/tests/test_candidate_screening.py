# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.candidate_screening import CandidateScreeningSession
from app.models.history import JobDescription, Resume
from app.services.screening_report_export_service import _build_report_context, _render_screening_html
from app.models.user import User


@pytest.fixture
def screening_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(analysis_router, prefix="/analysis")

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


def _create_recruiter(db_session, username: str, email: str) -> User:
    user = _create_user(db_session, username, email)
    user.role = "recruiter"
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _create_resume(db_session, *, user_id: int, name: str, skills: list[str], years_exp: int) -> Resume:
    resume = Resume(
        user_id=user_id,
        file_name=f"{name}.pdf",
        file_path=f"uploads/{name}.pdf",
        file_type="pdf",
        file_size=123,
        is_deleted=0,
        name=name,
        years_exp=years_exp,
        parsed_json={
            "name": name,
            "skills": skills,
            "years_exp": years_exp,
            "education": "本科",
            "project_experience": [
                {"name": "project-a", "tech": skills[:2], "desc": "负责 Python FastAPI 服务开发"}
            ],
        },
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _create_job(db_session, *, user_id: int, title: str = "Python 后端工程师") -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title=title,
        company="Test Co",
        location="Shanghai",
        salary_range="20k-30k",
        raw_text=f"{title} role",
        parsed_json={
            "title": title,
            "required_skills": ["python", "fastapi", "mysql"],
            "nice_to_have": ["redis", "docker"],
            "education_requirement": "本科",
            "experience_requirement": "2-4年",
            "keywords": ["api", "backend"],
        },
        source="manual",
        industry="AI",
        is_active=1,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_screen_candidates_returns_ranked_candidates(screening_client, db_session, monkeypatch):
    owner = _create_recruiter(db_session, "screen_owner", "screen_owner@example.com")
    job = _create_job(db_session, user_id=owner.id)
    best = _create_resume(db_session, user_id=owner.id, name="张三", skills=["python", "fastapi", "mysql", "redis"], years_exp=3)
    normal = _create_resume(db_session, user_id=owner.id, name="李四", skills=["python", "django"], years_exp=1)

    monkeypatch.setattr(
        "app.services.match_explainer_service.chat_json",
        lambda _prompt: {
            "overall": "整体匹配度良好",
            "reasons": {
                "skill": "技能较匹配",
                "project": "项目相关",
                "experience": "经验基本合适",
                "education": "学历满足要求",
                "keyword": "关键词覆盖尚可",
                "bonus": "加分项一般",
            },
            "risk_points": ["缺少部分加分项"],
            "suggestions": ["补充 Redis 项目经验"],
        },
    )

    resp = screening_client.post(
        "/analysis/screen-candidates",
        headers=_auth_headers(owner),
        json={"jd_id": job.id, "resume_ids": [normal.id, best.id], "top_k": 5},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["summary"]["total_candidates"] == 2
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["resume_id"] == best.id
    assert data["candidates"][1]["resume_id"] == normal.id
    assert data["candidates"][0]["candidate_name"] == "张三"
    assert "skills" in data["candidates"][0]["dimension_scores"]


def test_screen_candidates_rejects_foreign_resume(screening_client, db_session):
    owner = _create_recruiter(db_session, "screen_owner2", "screen_owner2@example.com")
    other = _create_user(db_session, "screen_other2", "screen_other2@example.com")
    job = _create_job(db_session, user_id=owner.id)
    foreign_resume = _create_resume(db_session, user_id=other.id, name="王五", skills=["python"], years_exp=2)

    resp = screening_client.post(
        "/analysis/screen-candidates",
        headers=_auth_headers(owner),
        json={"jd_id": job.id, "resume_ids": [foreign_resume.id], "top_k": 5},
    )

    assert resp.status_code == 404


def test_screen_candidates_rejects_candidate_role(screening_client, db_session):
    candidate = _create_user(db_session, "screen_candidate", "screen_candidate@example.com")
    job = _create_job(db_session, user_id=candidate.id)
    resume = _create_resume(db_session, user_id=candidate.id, name="候选人", skills=["python"], years_exp=2)

    resp = screening_client.post(
        "/analysis/screen-candidates",
        headers=_auth_headers(candidate),
        json={"jd_id": job.id, "resume_ids": [resume.id], "top_k": 5},
    )

    assert resp.status_code == 403


def test_save_and_export_screening_session(screening_client, db_session, monkeypatch):
    owner = _create_recruiter(db_session, "screen_owner3", "screen_owner3@example.com")
    job = _create_job(db_session, user_id=owner.id)
    resume = _create_resume(db_session, user_id=owner.id, name="赵六", skills=["python", "fastapi", "mysql"], years_exp=4)

    monkeypatch.setattr(
        "app.services.match_explainer_service.chat_json",
        lambda _prompt: {
            "overall": "整体匹配度较高",
            "reasons": {
                "skill": "技能命中较好",
                "project": "项目相关度较高",
                "experience": "经验满足要求",
                "education": "学历满足要求",
                "keyword": "关键词覆盖较好",
                "bonus": "有部分加分项",
            },
            "risk_points": ["系统设计待验证"],
            "suggestions": ["补充高并发案例"],
        },
    )

    save_resp = screening_client.post(
        "/analysis/screen-candidates/save",
        headers=_auth_headers(owner),
        json={"jd_id": job.id, "resume_ids": [resume.id], "top_k": 5, "name": "后端候选人初筛"},
    )
    assert save_resp.status_code == 200
    saved = save_resp.json()["data"]
    session_id = saved["id"]
    assert saved["name"] == "后端候选人初筛"

    list_resp = screening_client.get(
        "/analysis/screen-candidates/sessions",
        headers=_auth_headers(owner),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] == 1

    detail_resp = screening_client.get(
        f"/analysis/screen-candidates/sessions/{session_id}",
        headers=_auth_headers(owner),
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["result_payload"]["candidates"][0]["candidate_name"] == "赵六"

    export_resp = screening_client.get(
        f"/analysis/screen-candidates/sessions/{session_id}/export",
        headers=_auth_headers(owner),
    )
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    assert "赵六".encode("utf-8") in export_resp.content


def test_export_screening_session_docx_and_pdf(screening_client, db_session, monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))

    owner = _create_recruiter(db_session, "screen_owner4", "screen_owner4@example.com")
    job = _create_job(db_session, user_id=owner.id)
    resume = _create_resume(db_session, user_id=owner.id, name="钱七", skills=["python", "fastapi", "mysql"], years_exp=4)

    monkeypatch.setattr(
        "app.services.match_explainer_service.chat_json",
        lambda _prompt: {
            "overall": "整体匹配度较高",
            "reasons": {
                "skill": "技能命中较好",
                "project": "项目相关度较高",
                "experience": "经验满足要求",
                "education": "学历满足要求",
                "keyword": "关键词覆盖较好",
                "bonus": "有部分加分项",
            },
            "risk_points": ["系统设计待验证"],
            "suggestions": ["补充高并发案例"],
        },
    )

    save_resp = screening_client.post(
        "/analysis/screen-candidates/save",
        headers=_auth_headers(owner),
        json={"jd_id": job.id, "resume_ids": [resume.id], "top_k": 5, "name": "导出测试"},
    )
    session_id = save_resp.json()["data"]["id"]

    docx_path = tmp_path / "uploads" / "export" / "2026" / "06" / "screening.docx"
    pdf_path = tmp_path / "uploads" / "export" / "2026" / "06" / "screening.pdf"
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    docx_path.write_bytes(b"docx-bytes")
    pdf_path.write_bytes(b"pdf-bytes")

    monkeypatch.setattr(
        "app.api.analysis.export_screening_docx",
        lambda _session: "uploads/export/2026/06/screening.docx",
    )
    monkeypatch.setattr(
        "app.api.analysis.export_screening_pdf",
        lambda _session: "uploads/export/2026/06/screening.pdf",
    )

    docx_resp = screening_client.get(
        f"/analysis/screen-candidates/sessions/{session_id}/export",
        params={"format": "docx"},
        headers=_auth_headers(owner),
    )
    assert docx_resp.status_code == 200
    assert docx_resp.content == b"docx-bytes"

    pdf_resp = screening_client.get(
        f"/analysis/screen-candidates/sessions/{session_id}/export",
        params={"format": "pdf"},
        headers=_auth_headers(owner),
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content == b"pdf-bytes"


def test_screening_report_context_and_html_render():
    session = CandidateScreeningSession(
        id=99,
        name="后端候选人对比报告",
        jd_title="Python 后端工程师",
        company="Test Co",
        candidate_count=2,
        result_payload={
            "summary": {
                "jd_title": "Python 后端工程师",
                "company": "Test Co",
                "total_candidates": 2,
                "returned_candidates": 2,
                "recommendation_distribution": {"建议优先推进": 1, "建议进入复试": 1},
                "most_common_skill_gaps": [{"skill": "docker", "count": 1}],
            },
            "candidates": [
                {
                    "resume_id": 1,
                    "candidate_name": "张三",
                    "file_name": "zhangsan.pdf",
                    "years_exp": 4,
                    "skills": ["python", "fastapi", "mysql"],
                    "overall_score": 88,
                    "recommendation": "建议优先推进",
                    "overall_reason": "核心技能命中较全，经验贴近岗位。",
                    "risk_points": ["大型系统设计案例待验证"],
                    "optimization_suggestions": ["复试重点追问性能优化项目"],
                    "matched_skills": ["python", "fastapi"],
                    "missing_required_skills": ["docker"],
                    "dimension_scores": {
                        "skills": {"score": 90, "reason": "技能命中较全"},
                        "project": {"score": 85, "reason": "项目方向相关"},
                    },
                },
                {
                    "resume_id": 2,
                    "candidate_name": "李四",
                    "file_name": "lisi.pdf",
                    "years_exp": 2,
                    "skills": ["python"],
                    "overall_score": 72,
                    "recommendation": "建议进入复试",
                    "matched_skills": ["python"],
                    "missing_required_skills": ["docker"],
                    "dimension_scores": {},
                },
            ],
        },
    )

    context = _build_report_context(session)
    assert context["report_title"] == "后端候选人对比报告"
    assert context["top_candidate"]["candidate_name"] == "张三"
    assert context["skill_gaps"][0]["skill"] == "docker"

    html = _render_screening_html(context)
    assert "Top 候选人" in html
    assert "候选人明细" in html
    assert "张三" in html
    assert "大型系统设计案例待验证" in html
