"""Knowledge base request/response schemas."""

from typing import Any

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
    organization_id: int | None = None
    create_time: str | None = None


class KBDocumentResp(BaseModel):
    id: int
    title: str
    file_name: str
    file_type: str
    file_size: int | None = 0
    doc_type: str
    chunk_count: int = 0
    status: str
    error_msg: str | None = None
    organization_id: int | None = None
    create_time: str | None = None
    update_time: str | None = None


class KBListResp(BaseModel):
    total: int
    items: list[KBDocumentResp]


class KBSearchReq(BaseModel):
    query: str = Field(..., description="检索关键词")
    doc_type: str | None = Field(None, description="按文档类型过滤")
    top_k: int = Field(5, ge=1, le=20, description="返回数量")


class KBSearchResult(BaseModel):
    chunk_id: str
    text: str
    doc_title: str
    doc_type: str
    chunk_index: int
    score: float


class KBSearchResp(BaseModel):
    results: list[KBSearchResult]


class QueryRewriteReq(BaseModel):
    original_query: str = Field(..., min_length=1, description="用户原始问题")
    resume_summary: str | None = Field("", description="简历摘要")
    jd_summary: str | None = Field("", description="JD 摘要")
    doc_type: str | None = Field(None, description="按文档类型过滤")
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
    queries: list[dict[str, str]] = Field(default_factory=list, description="召回该切片的所有 query")


class QueryRewriteResp(BaseModel):
    original_query: str
    rewritten_queries: list[RewrittenQueryItem]
    retrieved_chunks: list[RetrievedChunkItem]
    total_chunks: int
    rag_confidence: dict[str, Any]
    rag_context: str
    references: list[dict[str, Any]]


class KBDocumentChunkResp(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str
    doc_title: str
    doc_type: str
