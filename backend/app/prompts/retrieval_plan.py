"""检索路由 prompt — Agentic RAG 的关键一步：让 LLM 先判断该查哪些知识源、各取多少。

输出 JSON 格式：
{
  "doc_types": {
    "resume_template": 3,
    "skill_model": 2,
    ...
  },
  "reasoning": "为什么这样选（一两句话）"
}

只输出**需要**的 doc_type；用不到的不要列出，由调用方按缺失处理（=0）。
"""

RETRIEVAL_PLAN_PROMPT = """你是一名 RAG 检索路由专家。给定一个用户分析需求与可选的简历/JD 摘要，你需要判断本次检索应该从哪些知识源各取多少条。

【用户检索意图】
{intent}

【检索 query】
{query}

【简历摘要（可能为空）】
{resume_summary}

【JD 摘要（可能为空）】
{jd_summary}

【可选的 8 类知识源】
- resume_template   优秀简历模板与表达
- jd_lib            岗位 JD 样例
- interview_q       面试题库
- skill_model       岗位能力模型
- industry_report   行业报告
- career_path       职业发展路径
- salary_market     薪资与市场数据
- transition_guide  校招社招转行指南

【路由规则】
1. 只选**对当前 query 真正有用**的知识源，宁少勿多。例如：
   - 简历优化场景 → resume_template + skill_model
   - 岗位匹配场景 → jd_lib + skill_model + (可选) industry_report
   - 面试准备场景 → interview_q + skill_model
   - 职业规划场景 → career_path + industry_report + salary_market + transition_guide
   - 综合分析场景 → 各类适度选取
2. 每个 doc_type 的 top_k 给一个 1~5 的整数，根据该源对 query 的重要程度分配。
3. 总检索条数控制在 6~15 条之间，避免上下文膨胀。
4. 没把握的源**不要**写入 doc_types。

【输出】严格输出 JSON，不要其他文字，不要 markdown 代码块：
{{
  "doc_types": {{ "resume_template": 3, "skill_model": 2 }},
  "reasoning": "需求聚焦简历优化，重点参考模板与能力模型"
}}
"""
