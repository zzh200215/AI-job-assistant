"""JD Pydantic 模型"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JDParsedSchema(BaseModel):
    """`JD_PARSE_PROMPT` 输出的结构断言（键名逐字照 `app/prompts/jd_parse.py:11-21`）。

    与 `ResumeParsedSchema` 同一套两档制：**不带默认值**（键必须存在）＋ `| None`（值允许 null），
    因为这支 prompt 原文就写着"缺失字段填 null 或空数组"。

    为什么值得为它单独立一个校验：`parse_truncation_radius.py` 量到已落库的 29 份解析结果里，
    `required_skills` 有 **10 份是 null、5 份是空数组**，只有 14 份真有值——而这支的产出正是模拟面试出题的输入。
    """

    model_config = ConfigDict(extra="ignore")

    title: str | None
    company: str | None
    location: str | None
    salary_range: str | None
    experience_requirement: str | None
    education_requirement: str | None
    responsibilities: list[str] | None
    required_skills: list[str] | None
    nice_to_have: list[str] | None
    keywords: list[str] | None


class JDCreateReq(BaseModel):
    title: str = Field(..., description="岗位名称")
    company: str = Field("", description="公司名，可为空")
    raw_text: str = Field(..., description="完整 JD 文本")


class JDCreateResp(BaseModel):
    id: int
    title: str
    company: str | None = None
    raw_text: str
    parsed: dict[str, Any] = {}


class JDParseResp(BaseModel):
    id: int
    title: str
    parsed: dict[str, Any] = {}
    salary_range: str | None = None
    location: str | None = None
