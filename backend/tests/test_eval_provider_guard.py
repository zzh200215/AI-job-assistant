"""provider 闸自己的测试：三向断言 + 一条反空转（D133）。

写这道闸的起因是我把 `eval_rag.py` 在真 provider 下连跑 4 次（本机 `.env` 是 qwen），
账上明写那件事未批。闸要比我的记性可靠，所以它本身必须有会红的测试。
"""

from __future__ import annotations

import pytest

from app.core import config
from scripts.provider_guard import MOCK, non_mock_providers, require_mock


def test_mock_settings_pass_the_gate(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", MOCK, raising=False)
    monkeypatch.setattr(config.settings, "EMBEDDING_PROVIDER", MOCK, raising=False)
    assert non_mock_providers() == {}
    assert require_mock("eval_rag.py") == MOCK


def test_real_provider_is_refused_with_the_mock_command(monkeypatch, capsys):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "qwen", raising=False)
    monkeypatch.setattr(config.settings, "EMBEDDING_PROVIDER", "qwen", raising=False)
    with pytest.raises(SystemExit) as caught:
        require_mock("eval_rag.py")
    assert caught.value.code == 2
    message = capsys.readouterr().err
    # 拒绝必须自带出路：照着能跑对的那条命令抄，而不是只说一句"不行"
    assert "LLM_PROVIDER=mock" in message and "EMBEDDING_PROVIDER=mock" in message
    assert "--allow-real" in message and "eval_rag.py" in message


def test_explicit_opt_in_is_honoured_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "qwen", raising=False)
    monkeypatch.setattr(config.settings, "EMBEDDING_PROVIDER", MOCK, raising=False)
    # 这一条只走 print/return，不发任何请求：测"允许"这半边不需要真花钱
    assert require_mock("eval_agent.py", allow_real=True) == "real"
    out = capsys.readouterr().out
    assert "LLM_PROVIDER" in out and "run-to-run" in out


def test_the_judge_reads_settings_not_a_constant(monkeypatch):
    """反空转：把两个值都改成 mock，判据必须跟着变空——否则上面几条绿得没有意义。"""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openai", raising=False)
    monkeypatch.setattr(config.settings, "EMBEDDING_PROVIDER", MOCK, raising=False)
    assert non_mock_providers() == {"LLM_PROVIDER": "openai"}
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", MOCK, raising=False)
    assert non_mock_providers() == {}


@pytest.mark.parametrize("script", ["eval_rag.py", "eval_recommend.py", "eval_agent.py"])
def test_every_eval_script_is_wired(script):
    """三个入口都得接线；漏一个就等于没闸。"""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "scripts" / script).read_text(encoding="utf-8")
    assert "require_mock(" in source, f"{script} 没调用 provider 闸"
    assert '"--allow-real"' in source, f"{script} 缺 --allow-real，argparse 会把 CI 的显式运行判成未知参数"
