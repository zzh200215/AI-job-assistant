"""JD 相关业务：创建 JD + 解析为结构化 JSON"""

from sqlalchemy.orm import Session

from app.models.history import JobDescription
from app.prompts.jd_parse import JD_PARSE_PROMPT
from app.schemas.jd import JDParsedSchema
from app.services.llm_service import chat_json
from app.services.parse_guard import guarded_parse
from app.utils.text_budget import JD_SECTIONS


def create_jd(db: Session, title: str, company: str, raw_text: str, user_id: int = None) -> JobDescription:
    # 用户创建/解析的 JD 必须盖当前租户标记，避免落到「NULL=平台共享」被全局归为平台岗位
    jd = JobDescription(user_id=user_id, title=title, company=company, raw_text=raw_text)
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd


def parse_and_save(db: Session, jd_id: int) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if not jd:
        raise ValueError(f"jd {jd_id} not found")

    parsed, meta = guarded_parse(
        raw_text=jd.raw_text or "",
        prompt_template=JD_PARSE_PROMPT,
        text_key="jd_text",
        schema=JDParsedSchema,
        chat=chat_json,
        # JD 的段落表与简历不同一族（任职要求最该活下来），见 `text_budget.JD_PRIORITY_ORDER` 的注释。
        sections=JD_SECTIONS,
    )

    jd.parsed_json = {**parsed, "_meta": meta} if meta else parsed
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
