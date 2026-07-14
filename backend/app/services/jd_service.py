"""JD 相关业务：创建 JD + 解析为结构化 JSON"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription
from app.prompts.jd_parse import JD_PARSE_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json


def create_jd(db: Session, title: str, company: str, raw_text: str, user_id: int = None) -> JobDescription:
    jd = JobDescription(user_id=user_id, title=title, company=company, raw_text=raw_text)
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd


def parse_and_save(db: Session, jd_id: int) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise ValueError(f"jd {jd_id} not found")

    prompt = render_prompt(JD_PARSE_PROMPT, jd_text=(jd.raw_text or "")[:4000])
    parsed: dict[str, Any] = chat_json(prompt)

    jd.parsed_json = parsed
    jd.salary_range = parsed.get("salary_range")
    jd.location = parsed.get("location")
    # 允许 AI 回填更准的 title / company
    if parsed.get("title"):
        jd.title = parsed["title"]
    if parsed.get("company"):
        jd.company = parsed["company"]

    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd
