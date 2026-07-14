"""Canonical prompt for JobAgent."""

PROMPT_VERSION = "job-agent-v1"

JOB_AGENT_PROMPT = """你是一名资深招聘分析师。请对以下岗位 JD 进行全面分析。

【JD原始数据】
{jd_json}

【任务】
请从以下维度分析这份 JD，输出 JSON：

{{
  "position_info": {{
    "title": "岗位名称",
    "company": "公司",
    "location": "地点",
    "salary_range": "薪资范围"
  }},
  "required_skills": [
    {{"skill": "技能名称", "level": "精通/熟练/了解", "importance": "核心/重要/加分"}}
  ],
  "responsibilities": [
    {{"responsibility": "职责描述", "weight": "主要/辅助"}}
  ],
  "hidden_requirements": [
    {{"requirement": "隐性要求", "reason": "推断依据"}}
  ],
  "experience_requirement": {{
    "years": "经验年数",
    "industry": "行业偏好",
    "background": "背景要求"
  }},
  "education_requirement": "学历要求",
  "key_challenges": ["该岗位的核心挑战"],
  "career_path": "可能的职业发展路径",
  "company_insight": "公司/行业背景分析",
  "overall_assessment": "岗位总体分析(100字以内)"
}}

输出 JSON，不要其他文字。
"""

__all__ = ["JOB_AGENT_PROMPT", "PROMPT_VERSION"]
