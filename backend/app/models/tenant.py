"""Tenant 配置模型（T2-1 定稿：organization 即租户）。

租户核心信息（品牌 / 计费 / 状态 / 域名主标识）落在 `organization`（见 organization.py）；
本文件承载租户附属配置：KV 配置（tenant_configs）与域名绑定（tenant_domain_bindings）。
`tenant_id` 字段值即 `organization.id`，按设计决策不加 DB 级外键（§4 外键策略）。
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base
from app.utils.time_helper import utc_now


class TenantConfig(Base):
    """租户 KV 配置：品牌增强项 / 功能开关 / 价格覆盖。

    config_key 命名约定：`brand.*`（favicon/login_bg/company/contact）、`feature.*`、`price.*`。
    """

    __tablename__ = "tenant_configs"
    __table_args__ = (UniqueConstraint("tenant_id", "config_key", name="uq_tenant_configs_key"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="归属租户 organization.id")
    config_key = Column(String(50), nullable=False, comment="配置键，如 brand.favicon / feature.xxx / price.xxx")
    config_value = Column(JSON, nullable=False, comment="配置值")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "config_key": self.config_key,
            "config_value": self.config_value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TenantDomainBinding(Base):
    """租户域名绑定（域名 ↔ organization），一个租户可绑多个域名（主域名 + 别名/演示域名）。

    域名解析（T2-3 `resolve_tenant_by_host`）查本表；`domain` 全局唯一。
    """

    __tablename__ = "tenant_domain_bindings"
    __table_args__ = (UniqueConstraint("domain", name="uq_tenant_domain"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="归属租户 organization.id")
    domain = Column(String(255), nullable=False, comment="域名（主域/www/子域/自定义域）")
    is_primary = Column(Integer, nullable=False, default=0, server_default="0", comment="是否主域名（每租户至多一个）")
    status = Column(String(20), nullable=False, default="active", server_default="active", comment="active/inactive")
    created_at = Column(DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "is_primary": self.is_primary,
            "status": self.status,
            "created_at": self.created_at,
        }
