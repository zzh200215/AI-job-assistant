"""最终报告汇总 Prompt：将所有分析结果汇总为一份完整报告"""

AGENT_REPORT_PROMPT = """你是一名专业的求职顾问，请将下面的招聘分析各环节结果汇总为一份完整、易读的最终报告。

【简历摘要】
{resume_summary}

【JD摘要】
{jd_summary}

【匹配度分析结果】
{match_result}

【简历优化建议】
{optimize_result}

【面试题】
{interview_result}

【职业规划】
{career_result}

【自我校验结果】
{self_check_result}

【要求】
将以上信息汇总为一份结构清晰的最终报告 JSON，包含：

{{
  "report_title": "岗位匹配度综合分析报告",
  "summary": {{
    "candidate_name": "候选人姓名",
    "target_position": "目标岗位",
    "target_company": "目标公司",
    "match_score": 82,
    "overall_evaluation": "一句话综合评价",
    "recommendation": "推荐 / 备选 / 不推荐"
  }},
  "match_analysis": {{
    "score": 82,
    "strengths": ["优势1", "优势2"],
    "gaps": ["短板1", "短板2"],
    "dimension_scores": {{
      "skills": 90,
      "experience": 80,
      "education": 75,
      "industry": 85
    }}
  }},
  "optimization_suggestions": {{
    "key_points": ["重要建议1", "重要建议2"],
    "quick_wins": ["立即可改的3个点"]
  }},
  "interview_guide": {{
    "key_questions_count": 4,
    "focus_areas": ["面试重点领域1", "领域2"],
    "weakness_preparation": "针对短板的准备建议"
  }},
  "career_planning": {{
    "current_status": {{"level":"","career_stage":"","strengths":[],"development_areas":[]}},
    "skill_gaps": [],
    "learning_roadmap": [],
    "short_term_plan": {{"timeline":"","goals":[],"actions":[]}},
    "mid_term_plan": {{"timeline":"","goals":[],"actions":[]}},
    "long_term_plan": {{"timeline":"","goals":[],"career_direction":""}},
    "overall_advice": ""
  }},
  "development_advice": {{
    "short_term": ["短期建议1"],
    "long_term": ["长期建议1"]
  }},
  "quality_assurance": {{
    "self_check_score": 85,
    "issues": ["已修正的问题"]
  }}
}}

输出 JSON，不要其他文字。
"""
