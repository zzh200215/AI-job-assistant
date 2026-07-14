"""Canonical prompt for ResumeAgent."""

PROMPT_VERSION = "resume-agent-v1"

RESUME_AGENT_PROMPT = """你是一名资深简历诊断专家。请对以下简历进行全面诊断。

【简历原始数据】
{resume_json}

【任务】
请从以下维度分析这份简历，输出 JSON：

{{
  "basic_info": {{
    "name": "姓名",
    "years_exp": 工作年限,
    "skills": ["技能列表"],
    "current_title": "当前职位",
    "education": "学历",
    "major": "专业"
  }},
  "strengths": [
    {{"aspect": "优势方面", "detail": "具体说明"}}
  ],
  "weaknesses": [
    {{"aspect": "问题方面", "severity": "高/中/低", "detail": "具体问题", "suggestion": "改进建议"}}
  ],
  "expression_quality": {{
    "score": 0-100,
    "issues": ["表达问题1", "表达问题2"],
    "tips": ["改进建议1"]
  }},
  "missing_keywords": ["建议补充的关键词"],
  "format_score": 0-100,
  "format_tips": ["排版建议"],
  "overall_assessment": "总体评价(100字以内)",
  "optimization_priority": [
    {{"item": "最优先修改项", "reason": "原因"}}
  ]
}}

输出 JSON，不要其他文字。
"""

__all__ = ["RESUME_AGENT_PROMPT", "PROMPT_VERSION"]
