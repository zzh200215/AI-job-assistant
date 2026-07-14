from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.job_pipeline import router as pipeline_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.job_pipeline import JobApplicationPipeline
from app.models.user import User


def _user(db_session, name: str) -> User:
    user = User(username=name, email=f"{name}@example.com", password=hash_password("abc12345"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _resume_version(db_session, user_id: int, label: str) -> tuple[Resume, ResumeVersion]:
    resume = Resume(
        user_id=user_id,
        file_name="candidate.pdf",
        file_path="uploads/candidate.pdf",
        file_type="pdf",
        file_size=1,
        is_deleted=0,
    )
    db_session.add(resume)
    db_session.commit()
    version = ResumeVersion(
        resume_id=resume.id,
        version_type="tailored",
        label=label,
        content="# Candidate\n\n## Skills\n- Python",
        format="md",
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return resume, version


def test_pipeline_tracks_owned_resume_version_and_summarizes_results(db_session):
    user = _user(db_session, "pipeline_tracking_owner")
    resume, version = _resume_version(db_session, user.id, "Python 后端定制版")
    second = JobApplicationPipeline(
        user_id=user.id,
        resume_id=resume.id,
        resume_version_id=version.id,
        resume_version_label=version.label,
        title="Backend Engineer II",
        company="Acme",
        stage="interview",
    )
    db_session.add(second)
    db_session.commit()

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(pipeline_router, prefix="/jobs")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        options = client.get("/jobs/pipeline/resume-versions", headers=_headers(user))
        assert options.json()["data"]["items"][0]["id"] == version.id

        created = client.post(
            "/jobs/pipeline",
            headers=_headers(user),
            json={
                "title": "Backend Engineer I",
                "company": "Acme",
                "stage": "applied",
                "resume_id": resume.id,
                "resume_version_id": version.id,
            },
        )
        assert created.json()["code"] == 0
        assert created.json()["data"]["resume_version_label"] == "Python 后端定制版"

        stats = client.get("/jobs/pipeline/resume-version-stats", headers=_headers(user))
        item = stats.json()["data"]["items"][0]
        assert item["submitted"] == 2
        assert item["interviews"] == 1
        assert item["interview_rate"] == 50.0

        feedback = client.put(
            f"/jobs/pipeline/{created.json()['data']['id']}",
            headers=_headers(user),
            json={
                "feedback_type": "hr_reply",
                "feedback_score": 4,
                "feedback_tags": ["沟通顺畅", "技能匹配"],
                "feedback_note": "已进入技术面安排。",
            },
        )
        assert feedback.json()["code"] == 0
        assert feedback.json()["data"]["feedback_score"] == 4
        assert feedback.json()["data"]["feedback_tags"] == ["沟通顺畅", "技能匹配"]


def test_pipeline_rejects_other_users_resume_version(db_session):
    owner = _user(db_session, "pipeline_tracking_version_owner")
    outsider = _user(db_session, "pipeline_tracking_outsider")
    _, version = _resume_version(db_session, owner.id, "Private version")

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(pipeline_router, prefix="/jobs")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        response = client.post(
            "/jobs/pipeline",
            headers=_headers(outsider),
            json={"title": "Attempt", "stage": "todo", "resume_version_id": version.id},
        )
        assert response.status_code == 200
        assert response.json()["code"] != 0
