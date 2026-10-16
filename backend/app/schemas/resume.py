"""简历 Pydantic 模型"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkExperienceItem(BaseModel):
    """工作经历的一项。**内层键一律可缺**——模型少写一个 start 不该让整份解析判废。"""

    model_config = ConfigDict(extra="ignore")

    company: str | None = None
    title: str | None = None
    start: str | None = None
    end: str | None = None
    desc: str | None = None


class ProjectExperienceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    role: str | None = None
    start: str | None = None
    end: str | None = None
    desc: str | None = None
    tech: list[str] | None = None


class ResumeParsedSchema(BaseModel):
    """`RESUME_PARSE_PROMPT` 输出的结构断言（键名逐字照 `app/prompts/resume_parse.py:13-28`）。

    **两档制是这条链的关键**，出处 `简历与面试优化.md` §4 P1.1 度量段第 1 条：两支 prompt 自己就指令
    "缺失字段填 null 或空数组"，所以"键必须存在"与"值必须非空"必须分开判——把字段做成必填非空，
    校验器会和 prompt 的指令对着干，一次通过率会被合法输出打红。
    写法上就是：**不带默认值**（键缺席即失败）＋ `| None`（值取 null 通过）。

    `extra="ignore"`：库里已存的 12/25 那份旧形状多一个顶层 `school`，历史行重解析时不该因此整条判废。
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None
    phone: str | None
    email: str | None
    years_exp: int | None
    education: str | None
    major: str | None
    current_company: str | None
    current_title: str | None
    skills: list[str] | None
    work_experience: list[WorkExperienceItem] | None
    project_experience: list[ProjectExperienceItem] | None
    self_evaluation: str | None


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
