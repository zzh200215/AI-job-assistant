"""C端求职助手 Pydantic Schemas"""

from pydantic import BaseModel, Field, field_validator

# ============================================================
# 求职目标
# ============================================================


class TargetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="目标名称")
    position: str = Field("", max_length=100, description="目标岗位关键词")
    industry: str = Field("", max_length=50, description="目标行业")
    cities: list[str] = Field(default_factory=list, description="目标城市列表")
    salary_min: int | None = Field(None, ge=1, description="最低薪资(K/月)")
    salary_max: int | None = Field(None, ge=1, description="最高薪资(K/月)")
    skills: list[str] = Field(default_factory=list, description="核心技能列表")
    priority: str = Field("medium", pattern="^(high|medium|low)$", description="优先级")
    is_primary: int = Field(0, ge=0, le=1, description="是否主目标")
    notes: str = Field("", max_length=2000, description="备注")
    config: dict = Field(default_factory=dict, description="扩展配置")

    @field_validator("salary_max")
    @classmethod
    def salary_max_ge_min(cls, v, info):
        if v is not None and info.data.get("salary_min") and v < info.data["salary_min"]:
            raise ValueError("salary_max 必须 >= salary_min")
        return v


class TargetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    position: str | None = Field(None, max_length=100)
    industry: str | None = Field(None, max_length=50)
    cities: list[str] | None = None
    salary_min: int | None = Field(None, ge=1)
    salary_max: int | None = Field(None, ge=1)
    skills: list[str] | None = None
    priority: str | None = Field(None, pattern="^(high|medium|low)$")
    status: str | None = Field(None, pattern="^(active|paused|achieved|archived)$")
    is_primary: int | None = Field(None, ge=0, le=1)
    notes: str | None = Field(None, max_length=2000)
    config: dict | None = None


# ============================================================
# 求职日记
# ============================================================


class JournalCreate(BaseModel):
    entry_type: str = Field("note", pattern="^(note|interview_log|offer_review|reflection)$")
    title: str = Field(..., min_length=1, max_length=200, description="标题")
    content: str = Field("", max_length=10000, description="内容")
    pipeline_id: int | None = Field(None, description="关联投递记录ID")
    jd_id: int | None = Field(None, description="关联JD ID")
    tags: list[str] = Field(default_factory=list, description="标签")
    mood: str = Field("", pattern="^(|great|good|neutral|bad|terrible)$", description="心情")
    rating: int = Field(0, ge=0, le=5, description="自评分 0-5")
    interview_role: str = Field("", max_length=50, description="面试官角色")
    interview_round: int = Field(0, ge=0, description="面试轮次")
    interview_format: str = Field("", max_length=30, description="面试形式")
    attachments: list[str] = Field(default_factory=list, description="附件URL列表")
    is_private: int = Field(1, ge=0, le=1, description="是否私密")


class JournalUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, max_length=10000)
    entry_type: str | None = Field(None, pattern="^(note|interview_log|offer_review|reflection)$")
    tags: list[str] | None = None
    mood: str | None = Field(None, pattern="^(|great|good|neutral|bad|terrible)$")
    rating: int | None = Field(None, ge=0, le=5)
    interview_role: str | None = Field(None, max_length=50)
    interview_round: int | None = Field(None, ge=0)
    interview_format: str | None = Field(None, max_length=30)
    attachments: list[str] | None = None
    is_private: int | None = Field(None, ge=0, le=1)


# ============================================================
# 用户偏好
# ============================================================


class NotificationPrefsUpdate(BaseModel):
    interview_reminder: bool | None = None
    offer_reminder: bool | None = None
    follow_up: bool | None = None
    jd_push: bool | None = None
    quiet_hours_start: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM")
    quiet_hours_end: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM")
    jd_push_frequency: str | None = Field(None, pattern="^(daily|weekly|never)$")


class PrivacyUpdate(BaseModel):
    profile_visible: bool | None = None
    share_anonymized_stats: bool | None = None


class DefaultsUpdate(BaseModel):
    default_resume_id: int | None = None
    default_target_id: int | None = None
    language: str | None = Field(None, pattern="^(zh-CN|en-US)$")
    theme: str | None = Field(None, pattern="^(light|dark)$")


# ============================================================
# 提醒
# ============================================================


class MatchJdsRequest(BaseModel):
    target_id: int | None = Field(None, description="指定求职目标ID，为空则匹配所有目标")
