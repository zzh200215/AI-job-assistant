from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.resume import router as resume_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.user import User


def _create_user(db_session, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("abc12345"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _create_resume(db_session, user_id: int) -> Resume:
    resume = Resume(
        user_id=user_id,
        file_name="workspace.pdf",
        file_path="uploads/workspace.pdf",
        file_type="pdf",
        file_size=12,
        is_deleted=0,
        parsed_json={
            "name": "李华",
            "phone": "13800138000",
            "email": "lihua@example.com",
            "skills": ["Python", "FastAPI"],
            "work_experience": [{"company": "Acme", "title": "开发", "desc": "提升接口性能"}],
            "project_experience": [{"name": "平台", "desc": "负责服务开发"}],
            "education": "本科",
        },
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _create_job(db_session, user_id: int) -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title="Python 后端工程师",
        company="Acme",
        raw_text="Python FastAPI",
        parsed_json={"required_skills": ["Python", "FastAPI", "MySQL"]},
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_resume_workspace_create_update_diff_and_ats(db_session):
    user = _create_user(db_session, "workspace_owner")
    resume = _create_resume(db_session, user.id)
    job = _create_job(db_session, user.id)

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(resume_router, prefix="/resume")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        create = client.post(
            f"/resume/{resume.id}/versions",
            headers=_headers(user),
            json={
                "content": "# 李华 | 13800138000 | lihua@example.com\n\n## 技能\n- Python、FastAPI\n\n## 工作经历\n- 优化接口耗时 35%\n\n## 项目经历\n- 平台\n\n## 教育背景\n- 本科",
                "label": "后端投递版",
                "target_jd_id": job.id,
            },
        )
        assert create.status_code == 200
        version = create.json()["data"]
        assert version["label"] == "后端投递版"
        assert version["target_jd_id"] == job.id

        versions = client.get(f"/resume/{resume.id}/versions", headers=_headers(user))
        assert versions.json()["data"]["original"]["content"]
        assert versions.json()["data"]["versions"][0]["id"] == version["id"]

        update = client.patch(
            f"/resume/{resume.id}/versions/{version['id']}",
            headers=_headers(user),
            json={"content": version["content"] + "\n- 覆盖 3 个核心服务"},
        )
        assert update.json()["code"] == 0

        decision = client.post(
            f"/resume/{resume.id}/versions/{version['id']}/suggestions",
            headers=_headers(user),
            json={"suggestion_id": "0", "decision": "accepted"},
        )
        assert decision.json()["data"]["suggestion_decisions"] == {"0": "accepted"}

        diff = client.get(
            f"/resume/{resume.id}/versions/diff",
            headers=_headers(user),
            params={"compare_version_id": version["id"]},
        )
        assert diff.json()["code"] == 0
        assert diff.json()["data"]["summary"]["added_lines"] > 0

        ats = client.post(
            f"/resume/{resume.id}/ats-preview",
            headers=_headers(user),
            json={"version_id": version["id"], "jd_id": job.id},
        )
        assert ats.json()["code"] == 0
        assert "Python" in ats.json()["data"]["keyword_coverage"]["matched"]
        saved = db_session.get(ResumeVersion, version["id"])
        assert saved.ats_snapshot["score"] == ats.json()["data"]["score"]


def test_resume_workspace_blocks_other_users_version_access(db_session):
    owner = _create_user(db_session, "workspace_owner_two")
    outsider = _create_user(db_session, "workspace_outsider")
    resume = _create_resume(db_session, owner.id)
    version = ResumeVersion(resume_id=resume.id, version_type="manual", content="# Private", format="md")
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(resume_router, prefix="/resume")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        response = client.patch(
            f"/resume/{resume.id}/versions/{version.id}",
            headers=_headers(outsider),
            json={"content": "# Stolen"},
        )
        assert response.status_code == 200
        assert response.json()["code"] != 0
