#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create or promote an admin user.

Usage examples:
    python scripts/create_admin.py --username admin --email admin@example.com --password 'StrongP@ssw0rd'
    python scripts/create_admin.py --username admin --email admin@example.com --password-env ADMIN_PASSWORD

Exit codes:
    0 - success
    1 - failure
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Allow imports from the backend package when running from repo root or backend dir.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.user_roles import ADMIN_ROLE  # noqa: E402
from app.models.user import User  # noqa: E402


# Mirrors the rules in app.schemas.auth._validate_password_strength so the
# script fails fast before touching the database.
def _validate_password_strength(password: str, username: str, email: str) -> None:
    if password != password.strip():
        raise ValueError("密码首尾不能包含空格")
    if len(password) < 8:
        raise ValueError("密码长度至少为 8 位")

    has_lower = bool(re.search(r"[a-z]", password))
    has_upper = bool(re.search(r"[A-Z]", password))
    has_digit = bool(re.search(r"\d", password))
    has_special = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password))
    categories = sum([has_lower, has_upper, has_digit, has_special])

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
    if args.password_env:
        value = os.environ.get(args.password_env)
        if not value:
            raise ValueError(f"环境变量 {args.password_env} 未设置或为空")
        return value
    if args.password:
        return args.password
    raise ValueError("请通过 --password 或 --password-env 提供密码")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote an admin user")
    parser.add_argument("--username", required=True, help="管理员用户名")
    parser.add_argument("--email", required=True, help="管理员邮箱")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--password", help="管理员密码（不建议在命令行明文传入）")
    group.add_argument("--password-env", help="存放管理员密码的环境变量名")
    parser.add_argument(
        "--force",
        action="store_true",
        help="如果用户已存在，强制将其角色更新为 admin 并重置密码",
    )
    args = parser.parse_args()

    username = args.username.strip()
    email = _normalize_email(args.email)

    try:
        password = _get_password(args)
        _validate_password_strength(password, username, email)
    except ValueError as exc:
        print(f"密码校验失败: {exc}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        existing = (
            db.query(User)
            .filter(
                (func.lower(User.username) == username.lower())
                | (func.lower(User.email) == email.lower())
            )
            .first()
        )

        if existing:
            if not args.force:
                print(
                    f"用户已存在 (id={existing.id}, username={existing.username}, "
                    f"role={existing.role})。如需更新为 admin 请添加 --force。",
                    file=sys.stderr,
                )
                return 1
            existing.role = ADMIN_ROLE
            existing.password = hash_password(password)
            if email.lower() != (existing.email or "").lower():
                existing.email = email
            db.commit()
            db.refresh(existing)
            print(f"已更新用户 {existing.username} (id={existing.id}) 为 admin 并重置密码")
        else:
            user = User(
                username=username,
                email=email,
                password=hash_password(password),
                role=ADMIN_ROLE,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"已创建 admin 用户 {user.username} (id={user.id})")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"数据库操作失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
