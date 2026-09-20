"""Organization tenancy and membership models.

T2-1 定稿：`organization` 即租户核心表，`tenant_id` 即 `organization.id`。
租户品牌 / 计费字段落在本表；KV 配置与域名绑定见 `tenant.py`。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint

from app.core.database import Base
from app.utils.time_helper import utc_now

# 组织/租户状态（T2-1 定稿：active / suspended / expired）
ORGANIZATION_STATUS_ACTIVE = "active"
ORGANIZATION_STATUS_SUSPENDED = "suspended"
ORGANIZATION_STATUS_EXPIRED = "expired"
ORGANIZATION_STATUSES = {
    ORGANIZATION_STATUS_ACTIVE,
    ORGANIZATION_STATUS_SUSPENDED,
    ORGANIZATION_STATUS_EXPIRED,
}

# 隔离模式（T2-1 定稿：默认共享表 + tenant_id；高安全客户可选独立 schema，本期只落字段）
ISOLATION_MODE_SHARED = "shared"
ISOLATION_MODE_SCHEMA = "schema"
ISOLATION_MODES = {ISOLATION_MODE_SHARED, ISOLATION_MODE_SCHEMA}


class Organization(Base):
    __tablename__ = "organization"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    owner_id = Column(BigInteger, nullable=False, index=True)
    status = Column(String(20), nullable=False, default=ORGANIZATION_STATUS_ACTIVE, index=True)
    sso_provider = Column(String(20), nullable=True)

    # ===== 租户品牌与计费（T2-1 定稿，迁移 0017 新增）=====
    industry = Column(String(50), nullable=True, comment="行业")
    logo_url = Column(String(500), nullable=True, comment="品牌 logo")
    primary_color = Column(String(20), nullable=True, comment="品牌主色 #RRGGBB")
    plan_tier = Column(
        String(20),
        nullable=False,
        default="free",
        server_default="free",
        index=True,
        comment="套餐: free/pro/enterprise",
    )
    admin_user_id = Column(BigInteger, nullable=True, comment="租户管理员用户 ID（创建时回填 owner_id）")
    expires_at = Column(DateTime, nullable=True, index=True, comment="订阅到期时间（过期 → expired，T4-3）")
    isolation_mode = Column(
        String(20),
        nullable=False,
        default=ISOLATION_MODE_SHARED,
        server_default=ISOLATION_MODE_SHARED,
        comment="隔离模式: shared/schema",
    )

    created_at = Column(DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "owner_id": self.owner_id,
            "status": self.status,
            "sso_provider": self.sso_provider,
            "industry": self.industry,
            "logo_url": self.logo_url,
            "primary_color": self.primary_color,
            "plan_tier": self.plan_tier,
            "admin_user_id": self.admin_user_id,
            "expires_at": self.expires_at,
            "isolation_mode": self.isolation_mode,
        }


class OrganizationMembership(Base):
    __tablename__ = "organization_membership"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_organization_membership_user"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")
    status = Column(String(20), nullable=False, default="active")
    joined_at = Column(DateTime, nullable=False, default=utc_now)


class OrganizationSSOIdentity(Base):
    __tablename__ = "organization_sso_identity"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "subject", name="uq_organization_sso_subject"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    subject = Column(String(200), nullable=False)
    user_id = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class OrganizationSSOState(Base):
    __tablename__ = "organization_sso_state"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    state_hash = Column(String(64), nullable=False, unique=True, index=True)
    organization_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
