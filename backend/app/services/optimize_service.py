"""
简历优化建议服务
- 当前被 match_service 一并调用；
- 拆出来便于前端单独触发「重新生成建议」
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import AnalysisRecord, JobDescription, Resume
from app.prompts.optimize import OPTIMIZE_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json
from app.utils.service_access import (
    get_accessible_job_for_user,
    get_owned_analysis_record,
    get_owned_resume,
)


def regenerate_optimize(db: Session, record_id: int, user_id: int | None = None) -> AnalysisRecord:
    record: AnalysisRecord = (
        get_owned_analysis_record(db, record_id, user_id) if user_id is not None else db.get(AnalysisRecord, record_id)
    )
    if not record:
        raise ValueError("record not found")

    resume = (
        get_owned_resume(db, record.resume_id, user_id) if user_id is not None else db.get(Resume, record.resume_id)
    )
    jd = (
        get_accessible_job_for_user(db, record.jd_id, user_id)
        if user_id is not None
        else db.get(JobDescription, record.jd_id)
    )
    if not resume or not jd:
        raise ValueError("resume or jd missing")

    prompt = render_prompt(
        OPTIMIZE_PROMPT,
        rag_context="",
        resume_json=json.dumps(resume.parsed_json or {}, ensure_ascii=False),
        jd_json=json.dumps(jd.parsed_json or {}, ensure_ascii=False),
    )
    result: dict[str, Any] = chat_json(prompt)
    record.optimize_suggestions = result
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
