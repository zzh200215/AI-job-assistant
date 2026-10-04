"""D107：把服务端的密码规则与前端那份镜像钉在一起。

前端 `src/utils/passwordRules.js` 是 `app/schemas/auth.py::_validate_password_strength` 的手抄镜像。
手抄的东西会漂，而这里漂了的后果不是风格问题：表单放行、服务端 422，`model_validator` 的 `loc` 又塌成
`body`，候选人屏幕上是一副英文骨架包着一句中文（docs/upgrade-plan.md D103 量过那一族，起因就是注册页
只要求"字母 + 数字"而服务端对 8–11 位要求 4 类里 3 类）。

所以这个文件做两件事：
  1. 同一张用例表打在服务端模型上，断言的**接受/拒绝**与表一致——表是从前端那份镜像的测试里
     逐条搬来的，两边任何一侧改了规则，另一侧的测试就会和这张表打架；
  2. 读 `frontend/src/constants/weakPasswords.js` 做集合相等断言，防住"清单各改各的"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterReq

FRONTEND_LIST = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants" / "weakPasswords.json"

# (password, username, email, 服务端是否接受)
CASES = [
    ("Abc12345!", "zhang", "zhang@example.com", True),
    ("abcdefgh", "zhang", "zhang@example.com", False),
    ("abcd1234", "zhang", "zhang@example.com", False),
    ("password123", "zhang", "zhang@example.com", False),
    ("Summer2024", "zhang", "zhang@example.com", True),
    ("summer2024", "zhang", "zhang@example.com", False),
    ("Abcd1234", "zhang", "zhang@example.com", False),
    ("abcdefg12", "zhang", "zhang@example.com", False),
    ("abcdefg12345", "zhang", "zhang@example.com", True),
    ("abcdefghijkl", "zhang", "zhang@example.com", False),
    ("abcdefgh12 ", "zhang", "zhang@example.com", False),
    (" abcd12345", "zhang", "zhang@example.com", False),
    ("zhangzhang", "zhangzhang", "zhang@example.com", False),
    ("zhang", "zhang", "zhang@example.com", False),
    ("abcd1234", "zhang", "abcd1234@example.com", False),
    ("Passw0rd!", "zhang", "zhang@example.com", True),
    ("qwe123", "zhang", "zhang@example.com", False),
    ("12345678", "zhang", "zhang@example.com", False),
    ("  ", "zhang", "zhang@example.com", False),
    ("A1b2C3d4e5", "Zhang", "Zhang@Example.COM", True),
    ("P@ssW0rd", "zhang", "zhang@example.com", False),
    ("PASSW0RD!", "zhang", "zhang@example.com", True),
]


def _accepted(password: str, username: str, email: str) -> bool:
    try:
        RegisterReq(username=username, email=email, password=password)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize(("password", "username", "email", "accept"), CASES)
def test_server_verdict_matches_the_shared_table(password, username, email, accept):
    assert _accepted(password, username, email) is accept, (
        f"服务端对 {password!r} 的判定变了；前端镜像 `src/utils/passwordRules.js` 必须一起改，"
        "否则表单放行的密码会换来一个 422"
    )


def test_frontend_case_table_covers_both_directions():
    """这张表不能只剩一边：全是拒绝或全是接受都说明它没在量东西。"""
    accepted = sum(1 for case in CASES if case[3])
    assert accepted >= 4, f"只有 {accepted} 条被接受，正向对照太薄"
    assert len(CASES) - accepted >= 10, "负向用例太少"


def test_weak_password_list_is_the_same_on_both_sides():
    from app.core.password_blacklist import _WEAK_PASSWORDS

    assert FRONTEND_LIST.exists(), f"找不到前端清单：{FRONTEND_LIST}"
    frontend = set(json.loads(FRONTEND_LIST.read_text(encoding="utf-8")))
    assert frontend, "前端清单解析出来是空的——解析器在数空气"
    backend = {p.lower() for p in _WEAK_PASSWORDS}
    assert len(frontend) == len(backend) == len(_WEAK_PASSWORDS), (
        f"条数对不上：前端 {len(frontend)}、后端小写后 {len(backend)}、后端原样 {len(_WEAK_PASSWORDS)}"
        "（小写后变小说明后端有只差大小写的两条，那会让两边判成员的结果不同）"
    )
    assert frontend == backend, (
        f"后端与前端的弱密码清单不再同一份：只在后端 {sorted(backend - frontend)}，"
        f"只在前端 {sorted(frontend - backend)}"
    )


def test_the_reader_of_the_frontend_list_is_not_blind():
    """反向证据。第一版这里是用正则读 JS 里的字符串字面量，prettier 把双引号换成单引号那天它读到
    0 条，而"两边都空所以相等"差点放行——同一族第十五次复发（尺子数的是文本/格式不是东西）。
    所以这条钉的是数量、形状与两条哨兵值，不是"能跑"。"""
    frontend = set(json.loads(FRONTEND_LIST.read_text(encoding="utf-8")))
    assert len(frontend) >= 50, f"只读到 {len(frontend)} 条，解析或文件出了问题"
    assert all(
        x == x.strip().lower() for x in frontend
    ), "清单里出现了带空格或大写的项，与后端 `strip().lower()` 的判成员方式不再等价"
    assert "abcd1234" in frontend and "password123" in frontend, "读到的不像那份清单"
