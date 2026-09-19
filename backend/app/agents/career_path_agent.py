"""职业方向推荐：方向、覆盖率与薪资来自岗位库统计，模型只负责排序与措辞。

历史上这个 prompt 只拿到简历摘要，却被要求给出匹配度与薪资区间——那类数字没有
任何来源。现在数值一律由 `career_evidence.derive_directions` 计算，模型只能在
给定的方向里选择并说明理由；理由只有在真实推理时才采用，降级时回落到规则句。
"""

from __future__ import annotations

import json
from typing import Any

from app.prompts.rendering import render_prompt
from app.services.career_evidence import CareerDirection
from app.services.llm_service import chat_json, get_llm_provenance, set_llm_trace_context

CAREER_PATH_PROMPT = """你是一名资深职业规划师。下面这些岗位方向是**从岗位库里统计出来的**，不是你想出来的。

【候选人背景】
{resume_summary}

【可选岗位方向（含真实样本）】
{directions_json}

每个方向给出：direction_key（锚点）、label、sample_count（样本岗位数）、
coverage（候选人已覆盖该方向明确要求的比例，可能为 null）、matched_skills、
gap_skills（按需求频次排序的缺失技能）、salary（样本岗位的可解析薪资）、
degraded 与 degrade_reasons（样本是否太薄）。

【任务】
从上面**已有**的方向里挑出值得投递的 5-8 个，按"先高度匹配、再可转型"排序，
每个方向写一句推荐理由，并给出summary。

【硬性规则】
1. direction_key 必须逐字取自上面的清单，不得新增、改写或猜测；
2. 不得输出任何数值：不写 match_score、百分比、薪资数字、样本数——这些系统已经
   给了，你重述就可能变成编造；
3. 理由只能引用清单里给出的技能名与事实，不得引入候选人简历或清单之外的信息；
4. degraded 为 true 的方向必须把样本不足写进理由里，且不要排在前面；
5. category 只能是"高度匹配"或"可转型"；
6. 若某方向没有可依据的信息，宁可少给几个方向，不要凑数。

输出 JSON：
{{
  "career_paths": [
    {{"direction_key": "", "category": "高度匹配 / 可转型", "reason": "30字以内", "seniority": "初级/中级/高级"}}
  ],
  "summary": "综合建议(50字以内)"
}}

只输出 JSON，不要其他文字。
"""

_VALID_CATEGORIES = ("高度匹配", "可转型")


def _summary_of(resume_data: dict[str, Any]) -> str:
    skills = resume_data.get("skills", [])
    if isinstance(skills, list):
        skills = [s if isinstance(s, str) else s.get("skill", "") for s in skills]

    exp_desc = "\n".join(
        [f"- {w.get('company', '')} {w.get('title', '')}: {(w.get('desc') or '')[:100]}" for w in (resume_data.get("work_experience") or [])[:3]]
    )
    proj_desc = "\n".join(
        [
            f"- {p.get('name', '')}: {(p.get('desc') or '')[:100]} (技术栈: {', '.join(p.get('tech', []) or [])})"
            for p in (resume_data.get("project_experience") or [])[:3]
        ]
    )
    return (
        f"技能: {', '.join([s for s in skills if s][:12])}\n"
        f"经验: {resume_data.get('years_exp', 0)}年\n"
        f"学历: {resume_data.get('education', '')} - {resume_data.get('major', '')}\n"
        f"当前职位: {resume_data.get('current_title', '')}\n"
        f"工作经历:\n{exp_desc}\n"
        f"项目经历:\n{proj_desc}"
    )


def rule_reason(direction: CareerDirection) -> str:
    """A reason that is true without the model, so prose can degrade quietly."""
    parts = []
    if direction.coverage is None:
        parts.append(f"岗位库里有 {direction.sample_count} 条「{direction.label}」类岗位，未列出可核对的硬性要求")
    else:
        percent = int(round(direction.coverage * 100))
        parts.append(f"该方向的明确要求你已覆盖 {len(direction.matched_skills)}/{direction.required_total}（约 {percent}%）")
    gaps = [row["skill"] for row in direction.gap_skills[:3]]
    if gaps:
        parts.append("主要缺口：" + "、".join(gaps))
    elif direction.coverage:
        parts.append("未见明显技能缺口")
    if direction.degraded:
        parts.append("注意：" + "；".join(direction.degrade_reasons))
    return "。".join(parts)[:120]


def rule_category(direction: CareerDirection) -> str:
    coverage = direction.coverage or 0
    return "高度匹配" if coverage >= 0.6 else "可转型"


def validate_career_paths(
    directions: list[CareerDirection], payload: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep only paths that point at a direction the library actually contains."""
    by_key = {direction.key: direction for direction in directions}
    raw = payload.get("career_paths") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return [], [{"direction_key": None, "reason": "malformed_response"}]

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            rejected.append({"direction_key": None, "reason": "not_an_object"})
            continue
        key = item.get("direction_key")
        direction = by_key.get(key) if isinstance(key, str) else None
        if direction is None:
            rejected.append({"direction_key": key if isinstance(key, str) else None, "reason": "unknown_direction"})
            continue
        if key in seen:
            rejected.append({"direction_key": key, "reason": "duplicate_direction"})
            continue
        seen.add(key)

        category = str(item.get("category") or "").strip()
        accepted.append(
            {
                "direction_key": key,
                "category": category if category in _VALID_CATEGORIES else rule_category(direction),
                "reason": str(item.get("reason") or "").strip(),
                "seniority": str(item.get("seniority") or "").strip(),
            }
        )

    return accepted, rejected


class CareerPathAgent:
    """职业方向推荐（数值由岗位库给出，模型只做排序与说明）"""

    def recommend(self, resume_data: dict[str, Any], directions: list[CareerDirection]) -> dict[str, Any]:
        """Rank pre-computed directions. Never invents a number."""
        if not directions:
            return {"career_paths": [], "summary": "", "reason_source": "rules", "rejected": []}

        set_llm_trace_context(
            {
                "source": "career_path_agent.recommend",
                "prompt_version": "career-path-evidence-v1",
                "direction_count": len(directions),
            }
        )
        prompt = render_prompt(
            CAREER_PATH_PROMPT,
            resume_summary=_summary_of(resume_data or {}),
            directions_json=json.dumps(
                [direction.to_dict() for direction in directions],
                ensure_ascii=False,
                indent=2,
            ),
        )
        try:
            result: dict[str, Any] = chat_json(prompt)
        except Exception:
            result = {}

        paths, rejected = validate_career_paths(directions, result)
        # A mocked or truncated answer must not be presented as analysis: the
        # candidate still gets a real reason, computed from the same evidence.
        real_model_output = get_llm_provenance().get("source") == "real"
        by_key = {direction.key: direction for direction in directions}

        for path in paths:
            direction = by_key[path["direction_key"]]
            if real_model_output and path["reason"]:
                path["reason_source"] = "model"
            else:
                path["reason"] = rule_reason(direction)
                path["reason_source"] = "rules"
            if not path.get("seniority"):
                path.pop("seniority", None)

        summary = str(result.get("summary") or "").strip() if real_model_output else ""
        if not summary:
            summary = (
                f"岗位库里共 {len(directions)} 个方向可按你的技能覆盖度排序；"
                "优先看覆盖度高且样本充足的类目。"
            )

        return {"career_paths": paths, "summary": summary, "reason_source": "model" if real_model_output else "rules", "rejected": rejected}
