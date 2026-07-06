# -*- coding: utf-8 -*-
"""岗位数据源 Pydantic Schema"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


# ==================== JobDataSource ====================

class DataSourceConfig(BaseModel):
    """数据源连接配置"""
    file_path: Optional[str] = None
    file_encoding: Optional[str] = "utf-8"
    search_query: Optional[str] = None
    api_url: Optional[str] = None
    api_method: Optional[str] = "GET"
    api_query: Optional[Dict[str, Any]] = None
    api_headers: Optional[Dict[str, str]] = None
    api_body: Optional[Dict[str, Any]] = None
    auth_type: Optional[str] = Field("none", pattern="^(none|bearer|api_key)$")
    auth_token: Optional[str] = None
    auth_key_name: Optional[str] = None
    auth_key_value: Optional[str] = None
    auth_in: Optional[str] = Field("header", pattern="^(header|query)$")
    auth_refresh_url: Optional[str] = None
    auth_refresh_method: Optional[str] = Field("POST", pattern="^(GET|POST)$")
    auth_refresh_query: Optional[Dict[str, Any]] = None
    auth_refresh_headers: Optional[Dict[str, str]] = None
    auth_refresh_body: Optional[Dict[str, Any]] = None
    auth_refresh_token_path: Optional[str] = "access_token"
    pagination_enabled: Optional[bool] = False
    page_param: Optional[str] = "page"
    page_start: Optional[int] = 1
    page_size_param: Optional[str] = "page_size"
    page_size: Optional[int] = 20
    max_pages: Optional[int] = 5
    rate_limit_ms: Optional[int] = 0
    retry_max_attempts: Optional[int] = 3
    retry_backoff_ms: Optional[int] = 500
    field_mapping: Optional[Dict[str, str]] = Field(default_factory=lambda: {
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
    })
    delimiter: Optional[str] = ","
    skip_header: Optional[bool] = True
    json_path: Optional[str] = None
    has_more_path: Optional[str] = None


class JobDataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_type: str = Field(..., pattern="^(csv|json|api|mock|arbeitnow)$")
    config: DataSourceConfig
    sync_interval: int = Field(0, ge=0)


class JobDataSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[DataSourceConfig] = None
    status: Optional[int] = Field(None, ge=0, le=1)
    sync_interval: Optional[int] = Field(None, ge=0)


class JobDataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: str
    config: Dict[str, Any]
    status: int
    last_sync_at: Optional[datetime] = None
    last_sync_log_id: Optional[int] = None
    sync_interval: int
    created_at: datetime
    updated_at: datetime


# ==================== JobSyncLog ====================

class JobSyncLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    status: str
    total_count: int
    success_count: int
    fail_count: int
    duplicate_count: int
    embed_count: int
    duration_ms: int
    error_msg: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None



# ==================== 同步参数 ====================

class SyncTriggerIn(BaseModel):
    dry_run: bool = Field(False, description="仅测试不写入")
    limit: int = Field(0, ge=0, description="限制条数, 0=不限制")


class SyncTestIn(BaseModel):
    pass


class SyncTestOut(BaseModel):
    connectable: bool
    sample: List[Dict[str, Any]] = Field(default_factory=list)
    message: str


class SyncResultOut(BaseModel):
    log_id: int
    status: str
    total_count: int
    success_count: int
    fail_count: int
    duplicate_count: int
    embed_count: int
    duration_ms: int
    message: str
