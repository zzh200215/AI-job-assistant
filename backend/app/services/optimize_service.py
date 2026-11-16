"""
简历优化建议服务
- 只给「重新生成建议」这一个入口用（`POST /analysis/{id}/optimize/regenerate`）；
  整条分析的优化建议由编排链路（`ResumeOptimizeAgent`）写；
- 2026-11-14 之前它还被 `match_service.run_full_analysis` 一并调用，那个一次性三步的接口
  （`POST /analysis/match`）与 match_service 一起出树了，见 `docs/真provider实测.md` §7
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
        # 这两句会经 `api_error(400, str(exc))` 原样上屏：写给候选人看，不是写给日志看。
        raise ValueError("找不到这条分析记录")

    resume = (
        get_owned_resume(db, record.resume_id, user_id) if user_id is not None else db.get(Resume, record.resume_id)
    )
    jd = (
        get_accessible_job_for_user(db, record.jd_id, user_id)
        if user_id is not None
        else db.get(JobDescription, record.jd_id)
    )
    if not resume or not jd:
        raise ValueError("找不到这份简历或目标岗位")

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
