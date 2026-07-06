# -*- coding: utf-8 -*-
"""简历 Pydantic 模型"""
from typing import Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime


class ResumeUploadResp(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_type: str
    file_size: int


class ResumeParseResp(BaseModel):
    id: int
    raw_text: str
    parsed: Dict[str, Any]
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    years_exp: Optional[int] = 0
    create_time: Optional[datetime] = None
