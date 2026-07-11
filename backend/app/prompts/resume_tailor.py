# -*- coding: utf-8 -*-
"""简历自适应改写 Prompt

核心能力：根据目标 JD，在保持事实真实性的前提下，调整简历的措辞、重点、结构，
生成一份专门针对该 JD 的定制版简历。
"""
RESUME_TAILOR_PROMPT = """你是一名资深简历优化专家。请根据候选人的原始简历和目标岗位JD，生成一份**专门针对该岗位定制**的简历。

【核心原则】
1. **绝不编造**：不能添加简历中不存在的经历、技能、学历或项目
2. **突出匹配**：将与JD高度相关的经历和技能前置、详写；弱关联的简写
3. **关键词对齐**：在简历中自然嵌入JD中的核心技能关键词（但仅限于候选人真实拥有的）
4. **量化成果**：将模糊描述改为具体数字（如"提升性能"→"提升40%"），可合理推算
5. **STAR法则**：项目/经历描述按 Situation-Task-Action-Result 结构调整
6. **语言调优**：使用与JD描述风格一致的专业术语

{rag_context}

【原始简历(JSON)】
{resume_json}

【目标岗位JD(JSON)】
{jd_json}

【输出要求】
返回以下 JSON 格式，不要输出任何其他文字：

{{
  "tailored_markdown": "完整的Markdown格式定制简历",
  "tailored_structured": {{
    "name": "姓名",
    "phone": "电话",
    "email": "邮箱",
    "summary": "个人简介(150字以内，突出与目标岗位的3-5个核心匹配点)",
    "skills": ["技能1", "技能2"],
    "experience": [
      {{"company": "公司", "position": "职位", "period": "时间",
        "highlights": ["量化成果1", "量化成果2"]}}
    ],
    "projects": [
      {{"name": "项目名", "role": "角色", "tech_stack": ["技术"],
        "highlights": ["成果1", "成果2"]}}
    ],
    "education": [
      {{"school": "学校", "major": "专业", "degree": "学历", "period": "时间"}}
    ]
  }},
  "tailoring_notes": {{
    "key_matches": ["匹配点1：...", "匹配点2：..."],
    "reordered_sections": ["调整说明1", "调整说明2"],
    "keywords_added": ["新增关键词1", "新增关键词2"],
    "highlights_adjusted": ["重点调整说明1"]
  }},
  "match_analysis": {{
    "overall_fit": "高/中/低",
    "strengths": ["优势1", "优势2"],
    "gaps": ["差距1", "差距2"],
    "suggestions": ["改进建议1", "改进建议2"]
  }}
}}

【Markdown格式规范】
# 姓名 | 电话 | 邮箱
## 个人简介
（3-5句话，突出与目标岗位的核心匹配点）
## 核心技能
- **分类**：与JD高度匹配的技能列表（置顶）
- **分类**：其他相关技能
## 工作经历
### 公司名称 · 职位 · 时间
- 量化成果描述（使用STAR法则）
## 项目经验
### 项目名 · 角色
- 技术栈：...
- 量化成果描述
## 教育背景
- 学校 · 专业 · 学历 · 时间
"""
