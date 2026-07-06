# -*- coding: utf-8 -*-
"""Mock 岗位数据源适配器 — 用于演示和测试"""
from typing import List
from .adapter import JobDataSourceAdapter, SourceRow


_MOCK_DATA = [
    {
        "title": "Python后端开发工程师",
        "company": "字节跳动",
        "location": "北京",
        "salary": "25K-45K·15薪",
        "experience": "3-5年",
        "education": "本科",
        "description": "负责后端微服务开发与架构设计，参与高并发系统建设。",
        "skills": "Python,FastAPI,MySQL,Redis,Docker",
        "industry": "互联网/科技",
        "url": "https://www.zhipin.com/job/mock-1",
    },
    {
        "title": "高级前端工程师",
        "company": "腾讯",
        "location": "深圳",
        "salary": "28K-50K·16薪",
        "experience": "5-10年",
        "education": "本科",
        "description": "负责核心业务前端架构设计与开发，推动前端工程化。",
        "skills": "Vue3,React,TypeScript,Webpack,Node.js",
        "industry": "互联网/科技",
        "url": "https://www.zhipin.com/job/mock-2",
    },
    {
        "title": "AI大模型工程师",
        "company": "月之暗面",
        "location": "北京",
        "salary": "40K-70K·16薪",
        "experience": "3-5年",
        "education": "硕士",
        "description": "负责大模型训练与微调，参与Agent框架和RAG系统研发。",
        "skills": "PyTorch,Transformers,LLM,RAG,Agent",
        "industry": "AI/大模型",
        "url": "https://www.zhipin.com/job/mock-3",
    },
    {
        "title": "Java高级工程师",
        "company": "蚂蚁集团",
        "location": "杭州",
        "salary": "30K-60K·16薪",
        "experience": "5-10年",
        "education": "本科",
        "description": "负责支付核心链路设计与开发，保障系统高可用。",
        "skills": "Java,Spring Cloud,MySQL,Kafka,分布式",
        "industry": "金融/科技",
        "url": "https://www.zhipin.com/job/mock-4",
    },
    {
        "title": "数据分析师",
        "company": "滴滴",
        "location": "北京",
        "salary": "20K-35K·15薪",
        "experience": "3-5年",
        "education": "本科",
        "description": "负责业务数据分析，支持产品决策和运营策略优化。",
        "skills": "SQL,Python,Tableau,统计学,A/B测试",
        "industry": "互联网/出行",
        "url": "https://www.zhipin.com/job/mock-5",
    },
]


_DEFAULT_FIELD_MAPPING = {
    "title": "title",
    "company": "company",
    "location": "location",
    "salary_range": "salary",
    "experience_requirement": "experience",
    "education_requirement": "education",
    "raw_text": "description",
    "skill_tags": "skills",
    "industry": "industry",
    "external_url": "url",
}


class MockJobSource(JobDataSourceAdapter):
    """Mock 数据源：返回固定演示数据"""

    def __init__(self, config):
        super().__init__(config)
        if not self._field_mapping:
            self._field_mapping = dict(_DEFAULT_FIELD_MAPPING)

    def connect(self) -> bool:
        return True

    def read(self, limit: int = 0) -> List[SourceRow]:
        items = _MOCK_DATA[:limit] if limit > 0 else _MOCK_DATA
        rows: List[SourceRow] = []
        for idx, raw in enumerate(items):
            mapped = self._map_fields(raw)
            rows.append(SourceRow(
                external_id=f"mock-{idx}",
                title=self._clean_text(mapped.get("title", "")),
                company=self._clean_text(mapped.get("company", "")),
                location=self._clean_text(mapped.get("location", "")),
                salary_range=self._clean_text(mapped.get("salary_range", "")),
                experience_requirement=self._clean_text(mapped.get("experience_requirement", "")),
                education_requirement=self._clean_text(mapped.get("education_requirement", "")),
                raw_text=self._clean_text(mapped.get("raw_text", "")),
                skill_tags=[s.strip() for s in str(mapped.get("skill_tags", "")).split(",") if s.strip()],
                industry=self._clean_text(mapped.get("industry", "")),
                external_url=self._clean_text(mapped.get("external_url", "")),
                raw=dict(raw),
            ))
        return rows
