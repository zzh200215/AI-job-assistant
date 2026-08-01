"""T2-2 租户模型单测：organization 即租户 + tenant_configs / tenant_domain_bindings。

验证（对应 T2-2 验收「模型单测通过」）：
1. Organization 携带租户字段，plan_tier / isolation_mode 有默认值；
2. 品牌/计费字段可写入；
3. tenant_configs 唯一约束 (tenant_id, config_key)，跨租户可复用同一 config_key；
4. tenant_configs.config_value JSON 存取；
5. tenant_domain_bindings 唯一约束 domain；
6. 一个租户可绑定多域名。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.organization import Organization
from app.models.tenant import TenantConfig, TenantDomainBinding


def _make_tenant(db, name: str = "测试租户", slug: str = "t-tenant", **overrides) -> Organization:
    org = Organization(name=name, slug=slug, owner_id=1, **overrides)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_tenant_defaults(db_session):
    org = _make_tenant(db_session)
    assert org.plan_tier == "free"
    assert org.isolation_mode == "shared"
    assert org.status == "active"
    # admin_user_id 由迁移回填 owner_id；新插入由业务层负责（organization API 设置 owner）
    assert org.admin_user_id is None


def test_tenant_brand_and_billing_fields_writable(db_session):
    org = _make_tenant(
        db_session,
        slug="brand-tenant",
        industry="教育培训",
        logo_url="https://cdn.example.com/logo.png",
        primary_color="#1677ff",
        plan_tier="pro",
        admin_user_id=2,
        expires_at=None,
    )
    assert org.industry == "教育培训"
    assert org.logo_url == "https://cdn.example.com/logo.png"
    assert org.primary_color == "#1677ff"
    assert org.plan_tier == "pro"
    assert org.admin_user_id == 2


def test_tenant_config_unique_key_per_tenant(db_session):
    tenant = _make_tenant(db_session, slug="cfg-tenant")
    db_session.add(TenantConfig(tenant_id=tenant.id, config_key="brand.favicon", config_value={"url": "a.png"}))
    db_session.commit()

    db_session.add(TenantConfig(tenant_id=tenant.id, config_key="brand.favicon", config_value={"url": "b.png"}))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 不同租户可复用同一 config_key
    other = _make_tenant(db_session, name="另一租户", slug="cfg-other")
    db_session.add(TenantConfig(tenant_id=other.id, config_key="brand.favicon", config_value={"url": "c.png"}))
    db_session.commit()


def test_tenant_config_value_json_roundtrip(db_session):
    tenant = _make_tenant(db_session, slug="cfg-json")
    db_session.add(
        TenantConfig(tenant_id=tenant.id, config_key="feature.xxx", config_value={"enabled": True, "price_cents": 9900})
    )
    db_session.commit()
    row = db_session.query(TenantConfig).filter_by(tenant_id=tenant.id).first()
    assert row.config_value == {"enabled": True, "price_cents": 9900}


def test_domain_binding_unique_domain(db_session):
    tenant = _make_tenant(db_session, slug="dom-tenant")
    db_session.add(TenantDomainBinding(tenant_id=tenant.id, domain="recruit.customer-a.com", is_primary=1))
    db_session.commit()

    db_session.add(TenantDomainBinding(tenant_id=tenant.id, domain="recruit.customer-a.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_domain_binding_multi_domain_per_tenant(db_session):
    tenant = _make_tenant(db_session, slug="dom-multi")
    db_session.add(TenantDomainBinding(tenant_id=tenant.id, domain="main.customer-b.com", is_primary=1))
    db_session.add(TenantDomainBinding(tenant_id=tenant.id, domain="demo.customer-b.com"))
    db_session.commit()
    rows = db_session.query(TenantDomainBinding).filter_by(tenant_id=tenant.id).all()
    assert len(rows) == 2
