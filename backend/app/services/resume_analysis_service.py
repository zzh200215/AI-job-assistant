"""
简历深度分析服务

对简历进行多维度量化评估，给出改进路线图。
与简历诊断(resume_agent)的区别：
- 诊断是快速反馈，分析是深度量化评估
- 分析包含5个维度的评分和改进路线图
- 分析可针对目标岗位做匹配差距分析
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import Resume
from app.prompts.rendering import render_prompt
from app.prompts.resume_analysis import RESUME_ANALYSIS_PROMPT
from app.services.llm_service import chat_json
from app.utils.service_access import get_owned_resume


def analyze_resume(
    db: Session,
    resume_id: int,
    target_position: str = "",
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    对简历进行深度分析。

    Args:
        db: 数据库会话
        resume_id: 简历ID
        target_position: 目标岗位（可选，用于匹配差距分析）
        user_id: 用户ID（用于权限校验）

    Returns:
        分析结果字典
    """
    # 获取简历
    if user_id is not None:
        resume = get_owned_resume(db, resume_id, user_id)
    else:
        resume = db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()

    if not resume:
        raise ValueError("简历不存在或无权限")

    # 获取简历JSON
    resume_json = resume.parsed_json or {}
    if not resume_json and resume.optimized_content:
        # 如果没有parsed_json但有优化内容，用原始内容
        resume_json = {"raw_markdown": resume.optimized_content}

    if not resume_json and resume.raw_text:
        resume_json = {"raw_text": resume.raw_text}

    if not resume_json:
        raise ValueError("简历内容为空，无法分析")

    # 调用LLM分析
    prompt = render_prompt(
        RESUME_ANALYSIS_PROMPT,
        resume_json=json.dumps(resume_json, ensure_ascii=False, indent=2),
        target_position=target_position or "未指定",
    )

    result: dict[str, Any] = chat_json(prompt)

    # 补充元数据
    result["resume_id"] = resume_id
    result["target_position"] = target_position
    result["analysis_version"] = "1.0"

    return result


def quick_score_resume(
    db: Session,
    resume_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    快速简历评分（不调用LLM，基于规则计算）。
    适用于列表页快速展示评分。
    """
    if user_id is not None:
        resume = get_owned_resume(db, resume_id, user_id)
    else:
        resume = db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()

    if not resume:
        raise ValueError("简历不存在")

    parsed = resume.parsed_json or {}
    score = 0
    issues = []

    # 1. 基本信息（20分）
    basic_fields = ["name", "phone", "email"]
    filled_basic = sum(1 for f in basic_fields if parsed.get(f))
    basic_score = min(20, filled_basic * 7)
    score += basic_score
    if filled_basic < 3:
        issues.append(f"基本信息缺失：缺少 {', '.join(f for f in basic_fields if not parsed.get(f))}")

    # 2. 工作经历（25分）
    experiences = parsed.get("work_experience", []) or parsed.get("experiences", [])
    if experiences:
        exp_score = min(25, len(experiences) * 8)
        # 检查是否有量化成果
        has_metrics = any(
            any(c in str(exp).lower() for c in ["%", "倍", "提升", "增长", "减少", "优化"]) for exp in experiences
        )
        if has_metrics:
            exp_score = min(25, exp_score + 5)
        else:
            issues.append("工作经历缺少量化成果，建议添加具体数字")
        score += exp_score
    else:
        issues.append("缺少工作经历")

    # 3. 项目经历（20分）
    projects = parsed.get("projects", []) or parsed.get("project_experience", [])
    if projects:
        proj_score = min(20, len(projects) * 7)
        score += proj_score
    else:
        issues.append("建议添加项目经历以突出实战能力")

    # 4. 技能（15分）
    skills = parsed.get("skills", []) or parsed.get("skill_list", [])
    if skills:
        skill_score = min(15, len(skills) * 2)
        score += skill_score
    else:
        issues.append("缺少技能列表")

    # 5. 教育背景（10分）
    education = parsed.get("education", []) or parsed.get("education_experience", [])
    if education:
        score += 10
    else:
        issues.append("缺少教育背景")

    # 6. 自我评价/总结（10分）
    summary = parsed.get("summary", "") or parsed.get("self_evaluation", "")
    if summary and len(str(summary)) > 20:
        score += 10
    elif summary:
        score += 5
        issues.append("自我评价过于简短，建议扩展")
    else:
        issues.append("建议添加个人简介/自我评价")

    return {
        "resume_id": resume_id,
        "quick_score": min(100, score),
        "grade": _score_to_grade(score),
        "issues": issues[:5],
        "module_check": {
            "basic_info": filled_basic >= 2,
            "work_experience": len(experiences) > 0,
            "projects": len(projects) > 0,
            "skills": len(skills) > 0,
            "education": len(education) > 0,
            "summary": bool(summary),
        },
    }


def _score_to_grade(score: int) -> str:
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "E"
