"""简历深度分析 —— 产出评估报告的模块一/二/三（结论段、七维评分、竞争分析）。

口径来自 `docs/resume-report-spec.md` §2–§3，七维表与等级映射住在
`app/services/resume_report_rubric.py`。两条从代码上读不出来的约束：

* **总分是七维之和，由这里算，不取模型自报的 `overall_score`。** 自报数只进
  `model_reported_total` 作对照——同一个量留两个权威，迟早有一边被当成真的（A4 在匹配分上
  踩过一次，同一处理方式见 `orchestration/strategies.py:_save_analysis_record`）。
* **维度缺失或越界判"未知"，总分随之未知**，绝不用下面的完整度分兜底。

`quick_score_resume` 是另一回事：它数的是"有多少模块被填了"，与本报告不同尺、不同等级口径。
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import Resume
from app.models.user import User
from app.prompts.rendering import render_prompt
from app.prompts.resume_report_overview import PROMPT_VERSION, RESUME_REPORT_OVERVIEW_PROMPT
from app.services import resume_report_rubric as rubric
from app.services.llm_service import chat_json, set_llm_trace_context
from app.utils.service_access import get_owned_resume


def salary_expectation_of(db: Session, user_id: int | None) -> str:
    """候选人自己填的期望薪资；没填就返回"未提供"，由模型按目标等级给参考区间。"""
    if user_id is None:
        return "未提供"
    user = db.get(User, user_id)
    if user is None:
        return "未提供"
    low = int(user.expected_salary_min or 0)
    high = int(user.expected_salary_max or 0)
    if low <= 0 and high <= 0:
        return "未提供"
    if low > 0 and high >= low:
        return f"{low}K–{high}K/月"
    return f"{max(low, high)}K/月（只填了一头）"


def _load_resume(db: Session, resume_id: int, user_id: int | None) -> Resume:
    if user_id is not None:
        resume = get_owned_resume(db, resume_id, user_id)
    else:
        resume = db.query(Resume).filter(Resume.id == resume_id, Resume.is_deleted == 0).first()
    if not resume:
        raise ValueError("简历不存在或无权限")
    return resume


def _resume_payload(resume: Resume) -> dict[str, Any]:
    if resume.parsed_json:
        return resume.parsed_json
    if resume.optimized_content:
        return {"raw_markdown": resume.optimized_content}
    if resume.raw_text:
        return {"raw_text": resume.raw_text}
    raise ValueError("简历内容为空，无法分析")


def _number_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(round(float(value)))


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str | int | float) and str(item).strip()]


def _text_or_empty(value: Any) -> str:
    """只收字符串。模型把这一位写成 dict/list 时，`str(...)` 会把 Python 表示法印进候选人的报告。"""
    return value.strip() if isinstance(value, str) else ""


def analyze_resume(
    db: Session,
    resume_id: int,
    target_position: str = "",
    user_id: int | None = None,
) -> dict[str, Any]:
    """按七维口径分析一份简历，返回报告模块一/二/三的结构化结果。

    模型只被允许给七维分与每维一段话；总分、等级、关键词汇总由本函数算。
    """
    resume = _load_resume(db, resume_id, user_id)
    resume_json = _resume_payload(resume)
    salary = salary_expectation_of(db, user_id)

    prompt = render_prompt(
        RESUME_REPORT_OVERVIEW_PROMPT,
        rubric_block=rubric.rubric_prompt_block(),
        resume_json=json.dumps(resume_json, ensure_ascii=False, indent=2),
        target_position=target_position or "未指定（按简历关键词自动识别方向）",
        salary_expectation=salary,
    )
    set_llm_trace_context(
        {
            "source": "resume_analysis_service.analyze_resume",
            "prompt_version": PROMPT_VERSION,
            "resume_id": resume_id,
            "user_id": user_id,
        }
    )
    # 这一发是同步等模型的，所以关掉思考链：D189/D195 在同一族简历 prompt 上量过，开思考链
    # 91.77s / 95.33s 返回的 `content` 长度为 0，关掉后 10.68s 出可用结果。
    result: dict[str, Any] = chat_json(prompt, disable_thinking=True)

    dimensions = rubric.read_dimensions(result.get("dimensions"))
    total = rubric.total_of(dimensions)
    competition = result.get("competition") if isinstance(result.get("competition"), dict) else {}
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    # 姓名从库里那一列来，不问模型：报告标题与下载文件名 `简历评估报告_{姓名}.html`
    # 都读这一位，让模型填就等于给它一个"猜错也没人报警"的字段。
    verdict["candidate_name"] = resume.name or ""

    return {
        "resume_id": resume_id,
        "target_position": target_position,
        "analysis_version": PROMPT_VERSION,
        "verdict": verdict,
        "dimensions": dimensions,
        "total_score": total,
        "grade": rubric.grade_of(total),
        "grade_desc": rubric.grade_desc_of(total),
        "grade_scale": rubric.grade_scale_block(),
        "to_next_grade": _text_list(result.get("to_next_grade")),
        # 对照证据，不上候选人的屏；它不得参与出分，由 tests/test_resume_report_overview.py 钉住。
        "model_reported_total": _number_or_none(result.get("overall_score")),
        "missing_keywords": rubric.missing_keywords_of(dimensions),
        "competition": {
            "positioning_badge": _text_or_empty(competition.get("positioning_badge")),
            "positioning_note": _text_or_empty(competition.get("positioning_note")),
            "cards": _text_list(competition.get("cards")),
            "gaps": _text_list(competition.get("gaps")),
            "advice": _text_list(competition.get("advice")),
            "salary_note": _text_or_empty(competition.get("salary_note")),
            "salary_provided": salary != "未提供",
        },
    }


def quick_score_resume(
    db: Session,
    resume_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    简历完整度检查（不调用LLM，基于规则计算）。适用于列表页快速展示。

    这是"有多少模块被填了"，不是"写得好不好"：各段分值由条目数量驱动，
    因此条目多而空的简历会拿到比条目少而实的简历更高的分。
    质量评价只能来自 analyze_resume 的模型输出。
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
        "measure": "completeness",
        "completeness_score": min(100, score),
        "completeness_grade": _score_to_grade(score),
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
    """完整度等级。与报告的七维评级不是同一把尺：这里量的是"填了多少个模块"，
    所以 70 就有 B，别把它读成模块二那个 B。"""
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
