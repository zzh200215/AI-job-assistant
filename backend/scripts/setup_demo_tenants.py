#!/usr/bin/env python3
"""
T5-1 双租户白标演示环境准备脚本。

准备两个演示租户：
  A 租户 = 客户视角（带品牌白标：logo / 主色 / 行业 / 域名 / pro 套餐）
  B 租户 = 默认视角（未配置品牌，用于对比「无白标」效果）

用法：
  python scripts/setup_demo_tenants.py --admin-password 'StrongP@ssw0rd'
  python scripts/setup_demo_tenants.py --admin-password-env DEMO_ADMIN_PASSWORD

前置：数据库迁移已完成（alembic upgrade head）；知识库种子已导入（可选，见 --seed-knowledge）。
脚本幂等：同 slug 已存在则跳过创建，直接复用。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.user_roles import ADMIN_ROLE  # noqa: E402
from app.models.organization import (  # noqa: E402
    Organization,
    OrganizationMembership,
)
from app.models.tenant import TenantDomainBinding  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.time_helper import utc_now_naive  # noqa: E402

# ===== 演示租户定义（可按需修改） =====
TENANT_A = {
    "name": "示例大学就业中心",
    "slug": "demo-university",
    "industry": "高等教育 · 就业指导",
    "primary_color": "#1A56DB",
    "logo_url": "/static/brand/demo-university-logo.png",  # 占位；上线前替换为真实 logo 地址
    "plan_tier": "pro",
    "months": 12,  # 到期时间 = now + 12 个月
    "domain": "career.demo-university.example.com",
}
TENANT_B = {
    "name": "示例机构（默认视角）",
    "slug": "demo-default",
    "industry": "职业教育",
    "primary_color": None,
    "logo_url": None,
    "plan_tier": "free",
    "months": 0,  # 不设到期
    "domain": None,
}

ADMIN_USERNAME = "demo_admin"
ADMIN_EMAIL = "demo_admin@example.com"


def _validate_admin_password(password: str, username: str, email: str) -> None:
    """复用 create_admin 的密码强度规则，避免弱密码进演示库。"""
    if password != password.strip():
        raise ValueError("密码首尾不能包含空格")
    if len(password) < 8:
        raise ValueError("密码长度至少为 8 位")
    has = {
        "lower": bool(re.search(r"[a-z]", password)),
        "upper": bool(re.search(r"[A-Z]", password)),
        "digit": bool(re.search(r"\d", password)),
        "special": bool(re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password)),
    }
    categories = sum(has.values())
    if len(password) >= 12:
        if categories < 2:
            raise ValueError("密码需至少包含字母、数字、特殊字符中的 2 种")
    else:
        if categories < 3:
            raise ValueError("密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种")
    if password.lower() == username.strip().lower():
        raise ValueError("密码不能与用户名相同")
    local = email.split("@")[0].strip().lower()
    if local and password.lower() == local:
        raise ValueError("密码不能与邮箱前缀相同")


def _get_password(args: argparse.Namespace) -> str:
    if args.admin_password_env:
        value = os.environ.get(args.admin_password_env)
        if not value:
            raise ValueError(f"环境变量 {args.admin_password_env} 未设置或为空")
        return value
    if args.admin_password:
        return args.admin_password
    raise ValueError("请通过 --admin-password 或 --admin-password-env 提供管理员密码")


def _ensure_admin(db, password: str) -> User:
    existing = (
        db.query(User)
        .filter(
            (func.lower(User.username) == ADMIN_USERNAME.lower())
            | (func.lower(User.email) == ADMIN_EMAIL.lower())
        )
        .first()
    )
    if existing:
        if existing.role != ADMIN_ROLE:
            existing.role = ADMIN_ROLE
            existing.password = hash_password(password)
            db.commit()
            print(f"[ADMIN] 已提升现有用户 {existing.username} (id={existing.id}) 为 admin")
        else:
            print(f"[ADMIN] 复用现有 admin 用户 {existing.username} (id={existing.id})")
        return existing
    user = User(
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        password=hash_password(password),
        role=ADMIN_ROLE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"[ADMIN] 已创建 admin 用户 {user.username} (id={user.id})")
    return user


def _ensure_tenant(db, spec: dict, admin: User) -> Organization:
    org = db.query(Organization).filter(Organization.slug == spec["slug"]).first()
    now = utc_now_naive()
    if org:
        print(f"[TENANT] 复用已有租户 {org.slug} (id={org.id})")
        return org
    expires_at = now + timedelta(days=30 * spec["months"]) if spec["months"] else None
    org = Organization(
        name=spec["name"],
        slug=spec["slug"],
        owner_id=admin.id,
        admin_user_id=admin.id,
        status="active",
        industry=spec["industry"],
        logo_url=spec["logo_url"],
        primary_color=spec["primary_color"],
        plan_tier=spec["plan_tier"],
        expires_at=expires_at,
        isolation_mode="shared",
    )
    db.add(org)
    db.flush()  # 取到 org.id

    # 租户管理员入成员表（owner 角色）
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == admin.id,
        )
        .first()
    )
    if not membership:
        db.add(
            OrganizationMembership(
                organization_id=org.id,
                user_id=admin.id,
                role="owner",
                status="active",
            )
        )

    # 绑定演示域名（仅主租户）
    if spec["domain"]:
        existing_domain = (
            db.query(TenantDomainBinding)
            .filter(TenantDomainBinding.domain == spec["domain"])
            .first()
        )
        if not existing_domain:
            db.add(
                TenantDomainBinding(
                    tenant_id=org.id,
                    domain=spec["domain"],
                    is_primary=1,
                    status="active",
                )
            )
            print(f"[DOMAIN] 已绑定 {spec['domain']} → 租户 {org.slug}")

    db.commit()
    db.refresh(org)
    print(
        f"[TENANT] 已创建租户 {org.slug} (id={org.id}, plan={org.plan_tier}, "
        f"brand={spec['primary_color'] or '默认'}, 到期={org.expires_at or '永不过期'})"
    )
    return org


def main() -> int:
    parser = argparse.ArgumentParser(description="准备双租户白标演示环境")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--admin-password", help="演示管理员密码")
    group.add_argument("--admin-password-env", help="存放演示管理员密码的环境变量名")
    parser.add_argument(
        "--seed-knowledge",
        action="store_true",
        help="同时导入内置知识库种子（docs/knowledge-seeds）",
    )
    args = parser.parse_args()

    try:
        password = _get_password(args)
        _validate_admin_password(password, ADMIN_USERNAME, ADMIN_EMAIL)
    except ValueError as exc:
        print(f"密码校验失败: {exc}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        admin = _ensure_admin(db, password)
        tenant_a = _ensure_tenant(db, TENANT_A, admin)
        tenant_b = _ensure_tenant(db, TENANT_B, admin)
    except Exception as exc:
        db.rollback()
        print(f"数据库操作失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print("\n===== 双租户演示环境就绪 =====")
    print(f"平台管理员: {ADMIN_USERNAME}@{ADMIN_EMAIL}")
    print(f"  A 租户（客户白标视角）: {TENANT_A['name']} slug={TENANT_A['slug']} id={tenant_a.id} plan={tenant_a.plan_tier}")
    if TENANT_A["domain"]:
        print(f"    演示域名: {TENANT_A['domain']}（需配置 DNS 解析到前端；未解析则用前端地址 + 租户切换）")
    print(f"  B 租户（默认视角）: {TENANT_B['name']} slug={TENANT_B['slug']} id={tenant_b.id} plan={tenant_b.plan_tier}")

    if args.seed_knowledge:
        print("\n[知识库] 请按 docs/演示脚本.md 运行 import_knowledge_seeds.py 导入种子知识。")

    print("\n登录后：平台管理员进入「运营后台 → 租户管理」可配置品牌 / 域名 / 套餐 / 续费。")
    print("详细演示流程见 docs/演示脚本.md。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
