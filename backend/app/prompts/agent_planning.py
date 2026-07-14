"""任务拆解 Prompt：AI 自动规划子任务"""

AGENT_PLANNING_PROMPT = """你是一名智能招聘系统的任务规划专家。请根据用户意图、简历信息和岗位 JD，拆解出需要执行的具体任务。

【任务上下文】
用户意图: {intent}
简历摘要: {resume_summary}
JD摘要: {jd_summary}

【要求】
请将分析过程拆解为 5-8 个子任务，每个子任务包含：
- step_name: 步骤标识
- description: 任务描述
- depends_on: 依赖的步骤（可选）
- expected_output: 预期输出

请按执行顺序排列，返回 JSON 数组：

[
  {{
    "step_name": "knowledge_retrieval",
    "description": "根据JD中的岗位名称和技能要求，从知识库检索相关简历模板、能力模型和面试题库",
    "depends_on": [],
    "expected_output": "检索到的知识切片列表"
  }},
  {{
    "step_name": "matching_analysis",
    "description": "对比简历和JD，生成匹配度评分和详细分析报告，结合检索到的行业能力模型",
    "depends_on": ["knowledge_retrieval"],
    "expected_output": "匹配度评分、维度分析、优劣势评估"
  }},
  {{
    "step_name": "resume_optimization",
    "description": "针对JD要求，参考优秀简历模板，生成具体的简历修改建议",
    "depends_on": ["matching_analysis"],
    "expected_output": "简历优化建议、关键词增删、表达改进"
  }},
  {{
    "step_name": "interview_question_generation",
    "description": "结合岗位要求、面试题库和候选人的简历短板，生成针对性面试题",
    "depends_on": ["matching_analysis"],
    "expected_output": "四类面试题(基础/项目/技术/场景)及参考答案"
  }},
  {{
    "step_name": "self_check",
    "description": "对上述分析结果进行自我校验，检查逻辑一致性和完整性",
    "depends_on": ["matching_analysis", "resume_optimization", "interview_question_generation"],
    "expected_output": "校验报告、问题列表、改进建议"
  }}
]

请根据实际意图调整任务列表，输出 JSON，不要其他文字。
"""
