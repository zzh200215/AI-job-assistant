"""共享表租户隔离 mixin（T2-1 定稿：organization 即租户，tenant_id = organization.id）。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column

# 内置默认租户 id（单租户存量数据归属）。2026-10-06 真删企业侧之后这里是唯一的出处，
# 列与索引都按 §2.3 保留：只停掉读写侧的租户逻辑，不动 schema。
DEFAULT_TENANT_ID = 1


class TenantScopedMixin:
    """业务表租户隔离字段。

    共享表隔离模式（isolation_mode=shared）：所有业务行带 tenant_id，查询/写入经
    2026-10-06 真删企业侧（D135）之后**没有任何读写侧走它了**：列保留、默认仍是内置租户 1，
    但候选人可见性只按 `user_id` 判（见 utils/job_access.py 与 utils/knowledge_access.py）。
    """

    tenant_id = Column(
        BigInteger,
        nullable=False,
        default=DEFAULT_TENANT_ID,
        server_default=str(DEFAULT_TENANT_ID),
        comment="归属租户 organization.id（T2-1 定稿，默认内置租户 1）",
    )
