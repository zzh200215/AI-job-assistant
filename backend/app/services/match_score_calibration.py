# -*- coding: utf-8 -*-
"""Deterministic score caps for obvious adjacent-role over-scoring cases."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


def infer_match_score_cap(resume_text: str, jd_text: str) -> Optional[int]:
    """Infer a hard upper bound when core JD evidence is clearly missing."""
    resume = _norm(resume_text)
    jd = _norm(jd_text)
    caps: list[int] = []

    if "全栈" in jd:
        has_frontend = _has_any(resume, ["前端", "react", "vue", "typescript", "javascript"])
        has_backend = _has_any(resume, ["后端", "node", "node.js", "fastapi", "django", "spring", "java", "go", "python"])
        has_db = _has_any(resume, ["postgresql", "mysql", "数据库", "sql", "redis"])
        if has_frontend and (not has_backend or not has_db):
            caps.append(55 if not has_backend and not has_db else 60)

    if "高级产品经理" in jd:
        resume_years = _first_years(resume)
        jd_min_years = _jd_min_years(jd)
        below_years = resume_years is not None and jd_min_years is not None and resume_years < jd_min_years
        missing_growth = not _has_any(resume, ["增长", "用户增长", "转化", "漏斗", "ab测试", "a/b"])
        missing_data = not _has_any(resume, ["数据", "指标", "sql", "bi", "分析"])
        missing_tech = not _has_any(resume, ["技术", "研发", "开发", "api", "架构"])
        if below_years and sum([missing_growth, missing_data, missing_tech]) >= 2:
            caps.append(50)

    if "技术项目经理" in jd:
        has_project_management = _has_any(resume, ["项目经理", "pmp", "项目管理", "项目全流程"])
        missing_agile = not _has_any(resume, ["敏捷", "scrum", "迭代"])
        no_tech_background = _has_any(resume, ["无技术背景", "没有技术背景", "非技术背景"])
        missing_tech_judgement = no_tech_background or not _has_any(
            resume, ["技术判断", "技术背景", "技术方案", "架构", "开发"]
        )
        missing_rd_collab = not _has_any(resume, ["研发", "开发团队", "工程师", "技术团队"])
        if has_project_management and missing_agile and missing_tech_judgement and missing_rd_collab:
            caps.append(40)

    return min(caps) if caps else None


def apply_match_score_cap(result: Dict[str, Any], resume_text: str, jd_text: str) -> Dict[str, Any]:
    """Clamp result['match_score'] when deterministic weak-fit caps apply."""
    score = max(0, min(100, int(result.get("match_score") or 0)))
    cap = infer_match_score_cap(resume_text, jd_text)
    result["match_score"] = min(score, cap) if cap is not None else score
    return result


def _norm(value: str) -> str:
    return (value or "").lower().replace(" ", "")


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower().replace(" ", "") in text for keyword in keywords)


def _first_years(text: str) -> Optional[int]:
    match = re.search(r"(\d+)\s*年", text)
    return int(match.group(1)) if match else None


def _jd_min_years(text: str) -> Optional[int]:
    range_match = re.search(r"(\d+)\s*[-~到至]\s*(\d+)\s*年", text)
    if range_match:
        return int(range_match.group(1))
    return _first_years(text)
