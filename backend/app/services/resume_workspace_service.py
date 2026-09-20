"""Pure helpers for the editable resume workspace."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.models.history import JobDescription


def build_markdown_diff(base_content: str, compare_content: str) -> dict[str, Any]:
    """Return line-oriented diff data that is straightforward for the client to render."""
    base_lines = (base_content or "").splitlines()
    compare_lines = (compare_content or "").splitlines()
    matcher = SequenceMatcher(a=base_lines, b=compare_lines)
    lines: list[dict[str, str]] = []
    added = 0
    removed = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            lines.extend({"type": "equal", "content": line} for line in base_lines[i1:i2])
        if tag in {"delete", "replace"}:
            removed += i2 - i1
            lines.extend({"type": "removed", "content": line} for line in base_lines[i1:i2])
        if tag in {"insert", "replace"}:
            added += j2 - j1
            lines.extend({"type": "added", "content": line} for line in compare_lines[j1:j2])

    return {
        "summary": {"added_lines": added, "removed_lines": removed, "unchanged_lines": len(base_lines) - removed},
        "lines": lines,
    }


def build_ats_snapshot(content: str, jd: JobDescription | None = None) -> dict[str, Any]:
    """Score the current Markdown deterministically, without changing the saved resume."""
    text = content or ""
    normalized = text.lower()
    headings = [line.strip()[2:].strip() for line in text.splitlines() if line.strip().startswith("## ")]
    section_terms = {
        "skills": ("技能", "skill", "技术栈"),
        "experience": ("工作", "经历", "experience", "职业"),
        "projects": ("项目", "project"),
        "education": ("教育", "学历", "education"),
    }
    found_sections = {
        key: any(term in " ".join(headings).lower() for term in terms) for key, terms in section_terms.items()
    }
    has_contact = bool(re.search(r"[\w.+-]+@[\w.-]+|1[3-9]\d{9}", text))
    has_metrics = bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|倍|万|亿|\+|人|项|次|天|月|年|k|w)", normalized))
    word_count = len(re.findall(r"[A-Za-z0-9+#.]+|[\u4e00-\u9fff]", text))

    structure_score = min(30, sum(found_sections.values()) * 6 + (6 if has_contact else 0))
    content_score = min(
        30, (12 if has_metrics else 0) + (10 if word_count >= 180 else 5 if word_count >= 80 else 0) + 8
    )

    keywords = _jd_keywords(jd)
    matched_keywords = [keyword for keyword in keywords if keyword.lower() in normalized]
    keyword_ratio = len(matched_keywords) / len(keywords) if keywords else 1
    keyword_score = round(keyword_ratio * 30)
    score = min(100, structure_score + content_score + keyword_score + 10)

    issues: list[str] = []
    if not has_contact:
        issues.append("缺少可识别的邮箱或手机号码")
    for key, present in found_sections.items():
        if not present:
            issues.append(f"缺少{_section_label(key)}栏目")
    if not has_metrics:
        issues.append("经历中缺少可识别的量化成果")
    if keywords and len(matched_keywords) < len(keywords):
        issues.append("目标岗位关键词覆盖不足")
    if word_count < 80:
        issues.append("正文过短，建议补充可验证的项目或成果")

    checks = [
        {"key": "contact", "label": "联系方式", "passed": has_contact},
        {"key": "sections", "label": "核心栏目", "passed": all(found_sections.values())},
        {"key": "metrics", "label": "量化成果", "passed": has_metrics},
        {"key": "keywords", "label": "岗位关键词", "passed": bool(keyword_ratio >= 0.6)},
    ]
    return {
        "score": score,
        "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D",
        "word_count": word_count,
        "sections": found_sections,
        "checks": checks,
        "issues": issues,
        "keyword_coverage": {
            "total": len(keywords),
            "matched": matched_keywords,
            "missing": [keyword for keyword in keywords if keyword not in matched_keywords],
        },
    }


def _jd_keywords(jd: JobDescription | None) -> list[str]:
    if not jd:
        return []
    parsed = jd.parsed_json or {}
    values = list(parsed.get("required_skills", []) or [])
    values.extend(parsed.get("keywords", []) or [])
    if jd.title:
        values.append(jd.title)
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))[:20]


def _section_label(key: str) -> str:
    return {"skills": "技能", "experience": "工作经历", "projects": "项目经历", "education": "教育背景"}[key]
