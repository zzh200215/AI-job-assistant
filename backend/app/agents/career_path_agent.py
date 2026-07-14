"""CareerPathAgent — 职业方向推荐智能体

根据用户简历技能、经验、学历，智能推荐多个可能的岗位方向。
"""

from typing import Any

from app.services.llm_service import chat_json

CAREER_PATH_PROMPT = """你是一名资深职业规划师。请根据候选人的技能和经验，推荐适合的岗位方向。

【候选人背景】
{resume_summary}

【任务】
分析候选人的技能组合、经验年限和学历背景，推荐 5-8 个适合投递的岗位方向。
要求:
1. 按匹配度从高到低排列
2. 每个方向说明推荐理由（基于技能重合度）
3. 标注需要提升的关键技能（如果有）
4. 区分"高度匹配"和"可转型"两类

输出 JSON：
{{
  "career_paths": [
    {{
      "title": "岗位名称",
      "match_score": 匹配度0-100,
      "category": "高度匹配 / 可转型",
      "reason": "推荐理由(30字以内)",
      "matched_skills": ["已具备的关键技能"],
      "gap_skills": ["需补充的技能"],
      "seniority": "初级/中级/高级",
      "salary_range": "薪资范围参考"
    }}
  ],
  "summary": "综合建议(50字以内)"
}}

只输出 JSON，不要其他文字。
"""


class CareerPathAgent:
    """职业方向推荐"""

    def recommend(self, resume_data: dict[str, Any]) -> dict[str, Any]:
        """根据简历数据推荐岗位方向"""
        skills = resume_data.get("skills", [])
        if isinstance(skills, list):
            skills = [s if isinstance(s, str) else s.get("skill", "") for s in skills]

        years_exp = resume_data.get("years_exp", 0)
        education = resume_data.get("education", "本科")
        major = resume_data.get("major", "")
        current_title = resume_data.get("current_title", "")
        work_exp = resume_data.get("work_experience", [])
        projects = resume_data.get("project_experience", [])

        # 构建摘要
        exp_desc = "\n".join(
            [f"- {w.get('company', '')} {w.get('title', '')}: {w.get('desc', '')[:100]}" for w in (work_exp or [])[:3]]
        )
        proj_desc = "\n".join(
            [
                f"- {p.get('name', '')}: {p.get('desc', '')[:100]} (技术栈: {', '.join(p.get('tech', []) or [])})"
                for p in (projects or [])[:3]
            ]
        )

        summary = (
            f"技能: {', '.join(skills[:12])}\n"
            f"经验: {years_exp}年\n"
            f"学历: {education} - {major}\n"
            f"当前职位: {current_title}\n"
            f"工作经历:\n{exp_desc}\n"
            f"项目经历:\n{proj_desc}"
        )

        prompt = CAREER_PATH_PROMPT.format(resume_summary=summary)
        result: dict[str, Any] = chat_json(prompt)
        return result
