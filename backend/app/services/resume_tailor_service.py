"""
简历自适应改写服务

根据目标 JD 生成定制版简历，核心区别于通用优化：
- 直接针对特定 JD 改写，不依赖 AnalysisRecord
- 保留匹配分析和改写说明
- 自动保存为新的 ResumeVersion
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume, ResumeVersion
from app.prompts.rendering import render_prompt
from app.prompts.resume_tailor import RESUME_TAILOR_PROMPT
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge
from app.utils.service_access import get_accessible_job_for_user, get_owned_resume


def tailor_resume_for_jd(
    db: Session,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    根据目标 JD 生成定制版简历。

    1. 读取简历和JD
    2. RAG检索相关简历模板和技能模型
    3. 调用LLM生成定制版简历
    4. 保存为 ResumeVersion（version_type="tailored"）
    5. 返回生成结果
    """
    resume = (
        get_owned_resume(db, resume_id, user_id)
        if user_id is not None
        else db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()
    )
    if not resume:
        raise ValueError("简历不存在")
    if not resume.parsed_json:
        raise ValueError("简历未解析，请先解析简历")

    jd = get_accessible_job_for_user(db, jd_id, user_id) if user_id is not None else db.get(JobDescription, jd_id)
    if not jd:
        raise ValueError("目标岗位不存在")

    resume_json = json.dumps(resume.parsed_json, ensure_ascii=False, indent=2)
    jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False, indent=2)

    # RAG检索简历模板和技能模型
    parsed_jd = jd.parsed_json or {}
    title = parsed_jd.get("title", "") or jd.title or ""
    skills = parsed_jd.get("required_skills", []) or []
    query = f"{title} {' '.join(skills[:5])}".strip()

    rag_parts = []
    for dtype in ["resume_template", "skill_model"]:
        results = search_knowledge(query, doc_type=dtype, top_k=3)
        if results:
            rag_parts.append(f"===== {dtype} =====")
            for r in results:
                rag_parts.append(f"【{r.get('doc_title', '')}】{r.get('text', '')[:300]}")
    rag_context = "\n".join(rag_parts)

    # 调用 LLM
    prompt = render_prompt(
        RESUME_TAILOR_PROMPT,
        rag_context=rag_context,
        resume_json=resume_json,
        jd_json=jd_json,
    )
    result: dict[str, Any] = chat_json(prompt)

    # 保存 Markdown 版本
    markdown = result.get("tailored_markdown", "")
    if markdown:
        md_version = ResumeVersion(
            resume_id=resume_id,
            version_type="tailored",
            content=markdown,
            format="md",
            label=f"{title or '目标岗位'} 定制版",
            target_jd_id=jd_id,
            change_log=result.get("tailoring_notes", {}),
        )
        db.add(md_version)

    # 保存结构化数据版本
    structured = result.get("tailored_structured", {})
    if structured:
        # 注入目标JD ID，便于前端区分不同JD的定制版本
        structured["_target_jd_id"] = jd_id
        structured["_target_title"] = title
        json_version = ResumeVersion(
            resume_id=resume_id,
            version_type="tailored",
            content=json.dumps(structured, ensure_ascii=False),
            format="json",
            label=f"{title or '目标岗位'} 定制版数据",
            target_jd_id=jd_id,
        )
        db.add(json_version)

    db.commit()

    return {
        "resume_id": resume_id,
        "jd_id": jd_id,
        "tailored_markdown": markdown,
        "tailored_structured": structured,
        "tailoring_notes": result.get("tailoring_notes", {}),
        "match_analysis": result.get("match_analysis", {}),
    }
