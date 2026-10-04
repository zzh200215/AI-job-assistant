"""§10.1 / D108：把「套餐到底 gates 了什么」钉成一条会响的清单。

订阅页此前对免费用户画 ✗，说「你没有 AI 简历优化」「每日分析只剩 3 次」，而服务端**没有任何调用方**
按那些键判过：`check_quota` 实现了 `deep_analysis` / `ats_check` / 每日额度，只有 `resume_count` 被
`resume.py` 真的用了。页面可以改措辞，但以后有人接上第二道门时，那一页的「各套餐一致」就又变成假话。
所以这条测试不是装饰：它扫 `app/api` 里所有 `check_quota` 的调用方并与名单比对。

名单变了就意味着行为变了，`frontend/src/features/billing/views/Subscription.vue` 里的
`ENFORCED_PLAN_KEYS` 必须一起改。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"
FRONTEND_PAGE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "features" / "billing" / "views" / "Subscription.vue"
)

# 唯一真门（resume.py 的简历数量）+ 通用查询端点（subscription.py）
QUOTA_CALLER_ALLOWLIST = {"resume.py", "subscription.py"}

# 这些资源在 subscription_service 里实现了，但今天没有任何路由按它们判
UNGATED_RESOURCES = ("deep_analysis", "ats_check", "daily_analysis", "daily_interview")


def _quota_call_lines() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for file in sorted(API_DIR.glob("*.py")):
        hits = [
            line.strip()
            for line in file.read_text(encoding="utf-8").splitlines()
            if "check_quota(" in line and not line.strip().startswith(("from ", "import "))
        ]
        if hits:
            found[file.name] = hits
    return found


def test_only_the_known_files_call_the_quota_gate():
    callers = _quota_call_lines()
    assert callers, "一个 check_quota 调用方都没扫到——这把尺子在数空气"
    assert set(callers) == QUOTA_CALLER_ALLOWLIST, (
        f"check_quota 的调用方变成了 {sorted(callers)}。新增额度门时，前端 Subscription.vue 的 "
        "ENFORCED_PLAN_KEYS 与权益表措辞必须一起改，否则那一页在说假话"
    )


def test_resume_is_the_only_gated_resource():
    resume_source = (API_DIR / "resume.py").read_text(encoding="utf-8")
    assert '"resume_count"' in resume_source, "resume.py 不再按 resume_count 判了：那条真门被拆了"

    callers = _quota_call_lines()
    routed = "\n".join(line for hits in callers.values() for line in hits)
    for resource in UNGATED_RESOURCES:
        assert f'"{resource}"' not in routed, f"{resource} 现在被某个路由判了；订阅页的「各套餐一致」措辞要重判"


@pytest.mark.parametrize("marker", ["ENFORCED_PLAN_KEYS", "各套餐一致"])
def test_frontend_still_carries_the_enforcement_list(marker):
    """反向证据的一半：前端若把名单或那句正面陈述删掉，这里必须红，而不是安静地放行。"""
    page = FRONTEND_PAGE.read_text(encoding="utf-8")
    assert marker in page, f"前端 Subscription.vue 里找不到 {marker}：权益表的诚实性没人管了"


def test_the_enforcement_list_holds_only_the_resume_key():
    page = FRONTEND_PAGE.read_text(encoding="utf-8")
    start = page.index("const ENFORCED_PLAN_KEYS")
    chunk = page[start : start + 200]
    open_at = chunk.index("new Set([") + len("new Set([")
    body = chunk[open_at : chunk.index("])")]
    # 只取引号里的成员，不比较整行文本：prettier 改引号或换行不该让这条红（D107 刚为这事红过一次）
    keys = set(re.findall(r"""['"]([^'"]+)['"]""", body))
    assert keys == {
        "resume_limit"
    }, f"前端名单不再是「只有简历数量」这一项：{sorted(keys)}——后端加了门就要同步改权益表措辞"
