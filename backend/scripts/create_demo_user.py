#!/usr/bin/env python3
"""
创建一个可直接演示的 demo 账号，并给它灌好演示数据。

用法：
    python scripts/create_demo_user.py
    python scripts/create_demo_user.py --force          # 已存在时重置密码并重灌
    DEMO_USER_PASSWORD='...' python scripts/create_demo_user.py

为什么要有这个脚本：注册之后的第一屏是六块空态，走一遍主链要点四次不同的按钮。
这个账号把这四次都替你做完了——登录进去就能看到有数据的首页、一份简历、五个岗位、
五条不同阶段的投递记录。

口令默认 `Demo@12345`：它能通过产品自己的密码策略（8 位以上、四类字符里占三类）。
**不要用 `demo1234` 这类口令当默认值**——那是"演示账号的密码过不了自家校验"的自相矛盾。

退出码：0 成功，1 失败。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.user_roles import CANDIDATE_ROLE  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.demo_seed_service import DEMO_RESUME, seed_demo_dataset  # noqa: E402

DEFAULT_USERNAME = "demo"
DEFAULT_EMAIL = "demo@example.com"
DEFAULT_PASSWORD = "Demo@12345"


def _apply_demo_profile(user: User) -> None:
    """把个人中心那几格填上，否则演示时那一页还是空的。"""
    parsed = DEMO_RESUME["parsed_json"]
    user.nickname = parsed.get("name") or user.nickname
    user.expected_position = parsed.get("expected_position") or user.expected_position
    user.expected_city = parsed.get("expected_city") or user.expected_city
    user.expected_salary_min = parsed.get("expected_salary_min") or user.expected_salary_min
    user.expected_salary_max = parsed.get("expected_salary_max") or user.expected_salary_max
    user.work_years = parsed.get("years_exp") or user.work_years
    user.education = "bachelor"
    user.job_seeking_status = "active"
    user.skill_tags = list(parsed.get("skills") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the demo account with seeded data")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument(
        "--password",
        default=os.environ.get("DEMO_USER_PASSWORD") or DEFAULT_PASSWORD,
        help="演示账号口令（默认取 DEMO_USER_PASSWORD，再回落到内置默认值）",
    )
    parser.add_argument("--force", action="store_true", help="已存在时重置密码并重灌演示数据")
    args = parser.parse_args()

    username = args.username.strip()
    email = args.email.strip().lower()

    db = SessionLocal()
    try:
        existing = (
            db.query(User)
            .filter((func.lower(User.username) == username.lower()) | (func.lower(User.email) == email.lower()))
            .first()
        )

        if existing and not args.force:
            print(
                f"用户已存在 (id={existing.id}, username={existing.username})。"
                "如需重置密码并重灌演示数据请加 --force。",
                file=sys.stderr,
            )
            return 1

        if existing:
            user = existing
            user.password = hash_password(args.password)
            user.role = CANDIDATE_ROLE
            print(f"已重置 {user.username} (id={user.id}) 的口令")
        else:
            user = User(
                username=username,
                email=email,
                password=hash_password(args.password),
                role=CANDIDATE_ROLE,
            )
            db.add(user)
            db.flush()
            print(f"已创建演示账号 {user.username} (id={user.id})")

        _apply_demo_profile(user)
        db.commit()

        data = seed_demo_dataset(db, user.id)
        print(
            "演示数据："
            f"简历 {'新建' if data['resume_created'] else '已存在'}、"
            f"岗位 +{data['jobs_inserted']}（跳过 {data['jobs_skipped']}）、"
            f"投递 +{data['applications_inserted']}（跳过 {data['applications_skipped']}）"
        )
        print(f"\n登录：{username} / {args.password}")
        print("口令可用 DEMO_USER_PASSWORD 覆盖；部署到公网前务必改掉。")
        return 0
    except Exception as exc:  # noqa: BLE001 - 脚本边界，交给调用方看原因
        db.rollback()
        print(f"失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
