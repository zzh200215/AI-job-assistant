# -*- coding: utf-8 -*-
"""Knowledge base request/response schemas."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


DOC_TYPE_CHOICES = [
    "resume_template",
    "jd_lib",
    "interview_q",
    "skill_model",
    "industry_report",
    "career_path",
    "salary_market",
    "transition_guide",
    "general",
]


class KBCreateReq(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="文档标题")
    doc_type: str = Field("general", description=f"文档类型: {DOC_TYPE_CHOICES}")


class KBUploadResp(BaseModel):
    id: int
    title: str
    file_name: str
    file_type: str
    file_size: int
    doc_type: str
    status: str
    create_time: Optional[str] = None


class KBDocumentResp(BaseModel):
    id: int
    title: str
    file_name: str
    file_type: str
    file_size: Optional[int] = 0
    doc_type: str
    chunk_count: int = 0
    status: str
    error_msg: Optional[str] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None


class KBListResp(BaseModel):
    total: int
    items: List[KBDocumentResp]


class KBSearchReq(BaseModel):
    query: str = Field(..., description="检索关键词")
    doc_type: Optional[str] = Field(None, description="按文档类型过滤")
    top_k: int = Field(5, ge=1, le=20, description="返回数量")


class KBSearchResult(BaseModel):
    chunk_id: str
    text: str
    doc_title: str
    doc_type: str
    chunk_index: int
    score: float


class KBSearchResp(BaseModel):
    results: List[KBSearchResult]


class QueryRewriteReq(BaseModel):
    original_query: str = Field(..., min_length=1, description="用户原始问题")
    resume_summary: Optional[str] = Field("", description="简历摘要")
    jd_summary: Optional[str] = Field("", description="JD 摘要")
    doc_type: Optional[str] = Field(None, description="按文档类型过滤")
    top_k_per_query: int = Field(5, ge=1, le=20, description="每个 query 返回数量")
    max_queries: int = Field(5, ge=1, le=10, description="最大改写 query 数")


class RewrittenQueryItem(BaseModel):
    query_text: str
    query_type: str
    purpose: str
    priority: int


class RetrievedChunkItem(BaseModel):
    chunk_id: str
    text: str
    doc_title: str
    doc_type: str
    chunk_index: int
    score: float
    final_score: float = 0
    rerank_score: float = 0
    rerank_source: str = ""
    query_used: str
    query_type: str
    queries: List[Dict[str, str]] = Field(default_factory=list, description="召回该切片的所有 query")


class QueryRewriteResp(BaseModel):
    original_query: str
    rewritten_queries: List[RewrittenQueryItem]
    retrieved_chunks: List[RetrievedChunkItem]
    total_chunks: int
    rag_confidence: Dict[str, Any]
    rag_context: str
    references: List[Dict[str, Any]]


class KBDocumentChunkResp(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str
    doc_title: str
    doc_type: str
