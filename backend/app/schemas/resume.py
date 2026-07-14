"""简历 Pydantic 模型"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ResumeUploadResp(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_type: str
    file_size: int


class ResumeParseResp(BaseModel):
    id: int
    raw_text: str
    parsed: dict[str, Any]
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    years_exp: int | None = 0
    create_time: datetime | None = None
