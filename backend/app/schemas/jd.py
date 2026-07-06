# -*- coding: utf-8 -*-
"""JD Pydantic 模型"""
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class JDCreateReq(BaseModel):
    title: str = Field(..., description="岗位名称")
    company: str = Field("", description="公司名，可为空")
    raw_text: str = Field(..., description="完整 JD 文本")


class JDCreateResp(BaseModel):
    id: int
    title: str
    company: Optional[str] = None
    raw_text: str
    parsed: Dict[str, Any] = {}


class JDParseResp(BaseModel):
    id: int
    title: str
    parsed: Dict[str, Any] = {}
    salary_range: Optional[str] = None
    location: Optional[str] = None
