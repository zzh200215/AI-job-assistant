"""共享表租户隔离 mixin（T2-1 定稿：organization 即租户，tenant_id = organization.id）。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column

# 内置默认租户 id（单租户存量数据归属，与 tenant_context.DEFAULT_TENANT_ID 保持一致）
DEFAULT_TENANT_ID = 1


class TenantScopedMixin:
    """业务表租户隔离字段。

    共享表隔离模式（isolation_mode=shared）：所有业务行带 tenant_id，查询/写入经
    `tenant_context.tenant_filter` / `stamp_tenant` 强制过滤（T2-4）。默认归属内置租户 1。
    """

    tenant_id = Column(
        BigInteger,
        nullable=False,
        default=DEFAULT_TENANT_ID,
        server_default=str(DEFAULT_TENANT_ID),
        comment="归属租户 organization.id（T2-1 定稿，默认内置租户 1）",
    )
