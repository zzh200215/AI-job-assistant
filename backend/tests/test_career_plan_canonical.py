"""P4 收口：完整规划（CareerAgent）的 skill_gaps 也要带 canonical。

`skill_gaps` 是模型自由文本（K8s / Kubernetes / k8s），画像里的技能弱点按
canonical 存。缺了这层，前端只能按拼写比，别名缺口就贴不上面试证据。
"""

from __future__ import annotations

from app.agents import career_agent as agent_mod
from app.orchestration.context import AgentContext


def _run_impl(monkeypatch, result):
    monkeypatch.setattr(agent_mod, "search_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(agent_mod, "chat_json", lambda prompt: result)
    return agent_mod.CareerAgent().run_impl(AgentContext(resume_id=1, jd_id=1, user_id=1))


def test_skill_gaps_get_canonical_identity(monkeypatch):
    result = _run_impl(
        monkeypatch,
        {"skill_gaps": [{"skill": "K8s"}, {"skill": "C++"}, {"skill": "关系型数据库"}]},
    )

    assert [gap["canonical"] for gap in result["skill_gaps"]] == [
        "kubernetes",
        "c-plus-plus",
        "关系型数据库",
    ]
    # 展示文本不动：页面仍显示模型写的那个名字。
    assert result["skill_gaps"][0]["skill"] == "K8s"


def test_missing_or_malformed_skill_gaps_pass_through(monkeypatch):
    result = _run_impl(monkeypatch, {"skill_gaps": "不适用"})
    assert result["skill_gaps"] == "不适用"

    rows = ["redis", {"skill": ""}, None]
    result = _run_impl(monkeypatch, {"skill_gaps": list(rows)})
    assert result["skill_gaps"] == rows
