import pytest

from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.user import User
from app.services import interview_service, match_service, optimize_service, resume_export_service
from app.services.match_score_service import canonical_match_score


def _create_user(db_session, username: str, email: str) -> User:
    from app.core.security import hash_password

    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_resume(db_session, *, user_id: int, parsed_json=None) -> Resume:
    resume = Resume(
        user_id=user_id,
        file_name="resume.pdf",
        file_path="uploads/resume.pdf",
        file_type="pdf",
        file_size=100,
        is_deleted=0,
        parsed_json=parsed_json or {"skills": ["python"], "name": "Tester"},
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _create_job(db_session, *, user_id, title: str, parsed_json=None) -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title=title,
        company="Test Co",
        location="Beijing",
        salary_range="20k-30k",
        raw_text=f"{title} role",
        parsed_json=parsed_json or {"title": title, "required_skills": ["python"], "keywords": ["api"]},
        source="manual",
        industry="AI",
        is_active=1,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _create_record(db_session, *, user_id: int, resume_id: int, jd_id: int) -> AnalysisRecord:
    record = AnalysisRecord(
        user_id=user_id,
        resume_id=resume_id,
        jd_id=jd_id,
        match_score=88,
        match_report={"summary": "ok"},
        optimize_suggestions={"items": []},
        interview_questions=[],
        remark="test",
        is_deleted=0,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_match_service_allows_owned_resume_with_public_jd(db_session, monkeypatch):
    owner = _create_user(db_session, "svc_owner", "svc_owner@example.com")
    resume = _create_resume(
        db_session,
        user_id=owner.id,
        parsed_json={"skills": ["python"], "name": "Owner"},
    )
    public_job = _create_job(
        db_session,
        user_id=None,
        title="Public Backend",
        parsed_json={"title": "Public Backend", "required_skills": ["python"], "keywords": ["fastapi"]},
    )

    monkeypatch.setattr(
        match_service,
        "build_rag_context_multi",
        lambda query, db, **kwargs: {
            "all": "",
            "resume_templates": "",
            "skill_models": "",
            "interview_questions": "",
        },
    )
    monkeypatch.setattr(match_service, "get_knowledge_references", lambda query, db, **kwargs: [])

    responses = iter(
        [
            {"match_score": 90, "reason": "good fit"},
            {"summary": "optimize"},
            {"questions": ["q1"]},
        ]
    )
    monkeypatch.setattr(match_service, "chat_json", lambda prompt: next(responses))

    record = match_service.run_full_analysis(
        db_session,
        resume.id,
        public_job.id,
        user_id=owner.id,
    )

    assert record.user_id == owner.id
    assert record.resume_id == resume.id
    assert record.jd_id == public_job.id
    # A4: the stored score is the canonical rubric score, not whatever number the
    # model happened to emit. This test is about access control, but the score
    # assertion now guards the single-source rule from regressing. AnalysisRecord
    # .match_score is an Integer column, so compare within one point rather than
    # depending on whether the database truncates or rounds.
    assert record.match_score != 90
    canonical = canonical_match_score(db_session, resume, public_job, user_id=owner.id, persist=False)["score"]
    assert abs(record.match_score - canonical) < 1


def test_match_service_blocks_cross_user_resume_service_bypass(db_session):
    owner = _create_user(db_session, "resume_owner", "resume_owner@example.com")
    outsider = _create_user(db_session, "resume_outsider", "resume_outsider@example.com")
    foreign_resume = _create_resume(db_session, user_id=owner.id)
    public_job = _create_job(db_session, user_id=None, title="Public Job")

    with pytest.raises(ValueError):
        match_service.run_full_analysis(
            db_session,
            foreign_resume.id,
            public_job.id,
            user_id=outsider.id,
        )


def test_optimize_and_interview_services_block_cross_user_record(db_session):
    owner = _create_user(db_session, "record_owner", "record_owner@example.com")
    outsider = _create_user(db_session, "record_outsider", "record_outsider@example.com")
    resume = _create_resume(db_session, user_id=owner.id)
    job = _create_job(db_session, user_id=owner.id, title="Private Job")
    record = _create_record(db_session, user_id=owner.id, resume_id=resume.id, jd_id=job.id)

    with pytest.raises(ValueError):
        optimize_service.regenerate_optimize(db_session, record.id, user_id=outsider.id)

    with pytest.raises(ValueError):
        interview_service.regenerate_interview(db_session, record.id, user_id=outsider.id)


def test_resume_export_service_blocks_cross_user_resume_generation(db_session):
    owner = _create_user(db_session, "export_owner", "export_owner@example.com")
    outsider = _create_user(db_session, "export_outsider", "export_outsider@example.com")
    resume = _create_resume(db_session, user_id=owner.id)

    with pytest.raises(ValueError):
        resume_export_service.generate_optimized(db_session, resume.id, user_id=outsider.id)


def test_resume_export_service_blocks_cross_user_resume_exports(db_session):
    owner = _create_user(db_session, "doc_owner", "doc_owner@example.com")
    outsider = _create_user(db_session, "doc_outsider", "doc_outsider@example.com")
    resume = _create_resume(db_session, user_id=owner.id)

    with pytest.raises(ValueError):
        resume_export_service.export_docx(resume.id, db=db_session, user_id=outsider.id)

    with pytest.raises(ValueError):
        resume_export_service.export_pdf(resume.id, db=db_session, user_id=outsider.id)
