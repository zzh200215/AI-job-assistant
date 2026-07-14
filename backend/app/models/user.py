"""用户 ORM 模型。"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, Text

from app.core.database import Base
from app.core.user_roles import CANDIDATE_ROLE
from app.utils.time_helper import utc_now

# 求职状态常量
JOB_SEEKING_STATUS_ACTIVE = "active"  # 在职看机会
JOB_SEEKING_STATUS_URGENT = "urgent"  # 离职急找
JOB_SEEKING_STATUS_OBSERVING = "observing"  # 观望中
JOB_SEEKING_STATUS_NOT_LOOKING = "not_looking"  # 暂不考虑
JOB_SEEKING_STATUSES = {
    JOB_SEEKING_STATUS_ACTIVE,
    JOB_SEEKING_STATUS_URGENT,
    JOB_SEEKING_STATUS_OBSERVING,
    JOB_SEEKING_STATUS_NOT_LOOKING,
}


class User(Base):
    __tablename__ = "tb_user"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    email = Column(String(100), unique=True)
    role = Column(String(20), nullable=False, default=CANDIDATE_ROLE, server_default=CANDIDATE_ROLE)

    # ===== 求职者个人资料 =====
    avatar_url = Column(String(500), default="", comment="头像 URL")
    nickname = Column(String(50), default="", comment="昵称")
    phone = Column(String(20), default="", comment="手机号")
    bio = Column(Text, default="", comment="个人简介")

    # ===== 求职意向 =====
    job_seeking_status = Column(String(20), default="", comment="求职状态: active/urgent/observing/not_looking")
    expected_position = Column(String(200), default="", comment="期望岗位，逗号分隔")
    expected_city = Column(String(200), default="", comment="期望城市，逗号分隔")
    expected_salary_min = Column(Integer, default=0, comment="期望最低月薪(K)")
    expected_salary_max = Column(Integer, default=0, comment="期望最高月薪(K)")
    expected_industry = Column(String(200), default="", comment="期望行业，逗号分隔")
    work_years = Column(Integer, default=0, comment="工作年限")
    education = Column(String(20), default="", comment="最高学历: high_school/associate/bachelor/master/phd")
    current_employer = Column(String(200), default="", comment="当前公司")
    current_position = Column(String(200), default="", comment="当前职位")

    # ===== 扩展信息 =====
    skill_tags = Column(JSON, comment="技能标签列表")
    social_links = Column(JSON, comment="社交链接: {github, linkedin, blog 等}")

    # ===== 用户偏好设置 =====
    default_resume_id = Column(BigInteger, comment="默认简历ID")
    default_target_id = Column(BigInteger, comment="默认求职目标ID")
    notification_preferences = Column(
        JSON,
        comment="通知偏好: {interview_reminder, offer_reminder, follow_up, jd_push, quiet_hours_start, quiet_hours_end}",
    )
    privacy_settings = Column(JSON, comment="隐私设置: {profile_visible, share_anonymized_stats}")
    language = Column(String(10), default="zh-CN", comment="界面语言")
    theme = Column(String(10), default="light", comment="主题: light/dark")
    email_verified = Column(Integer, default=0, comment="邮箱是否已验证: 0=未验证, 1=已验证")
    active_organization_id = Column(BigInteger, nullable=True, comment="当前组织工作区 ID")

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def get_notification_preferences(self) -> dict:
        """获取通知偏好（带默认值）"""
        defaults = {
            "interview_reminder": True,
            "offer_reminder": True,
            "follow_up": True,
            "jd_push": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "jd_push_frequency": "daily",
        }
        prefs = self.notification_preferences or {}
        return {**defaults, **prefs}

    def get_privacy_settings(self) -> dict:
        """获取隐私设置（带默认值）"""
        defaults = {
            "profile_visible": False,
            "share_anonymized_stats": False,
        }
        settings = self.privacy_settings or {}
        return {**defaults, **settings}
