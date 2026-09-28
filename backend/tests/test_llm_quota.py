"""E28：真实 provider 调用按用户限额（`app/core/llm_quota.py`）。

三条约定各测一遍，因为它们每一条都对应一种误伤方式：mock 不扣（否则测试套件被自己的闸拦掉）、
认不出用户不扣（否则全员共用一份额度）、额度存储坏了不扣（否则 Redis 抖一下就人人 429）。
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from app.core import llm_quota
from app.core.config import settings
from app.core.llm_quota import LLMQuotaExceededError, charge_if_real_provider, set_billing_user
from app.core.security import create_access_token, hash_password
from app.main import llm_quota_handler
from app.services import llm_service


@pytest.fixture(autouse=True)
def isolated_quota(monkeypatch):
    """每个用例一套内存计数，并且默认按"真实 provider"来测。"""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "LLM_CALLS_PER_USER_PER_MINUTE", 3)
    llm_quota.reset_for_tests()
    yield
    llm_quota.reset_for_tests()


def test_the_budget_blocks_the_call_after_it_is_spent():
    set_billing_user("user-A")
    for _ in range(3):
        charge_if_real_provider(provider="openai")  # 不抛就是放行

    with pytest.raises(LLMQuotaExceededError):
        charge_if_real_provider(provider="openai")


def test_a_different_user_gets_a_fresh_budget():
    set_billing_user("user-A")
    for _ in range(3):
        charge_if_real_provider(provider="openai")
    with pytest.raises(LLMQuotaExceededError):
        charge_if_real_provider(provider="openai")

    set_billing_user("user-B")
    charge_if_real_provider(provider="openai")  # 不该抛


def test_mock_provider_is_never_charged():
    """否则整个测试套件（conftest 钉 mock）会被这个闸改掉行为。"""
    set_billing_user("user-A")
    for _ in range(20):
        charge_if_real_provider(provider="mock")


def test_an_unattributable_call_is_not_charged():
    """fail-open：没身份就宁可不限，也不能把所有人的调用记到第一个人头上。"""
    for _ in range(20):
        charge_if_real_provider(provider="openai")


def test_a_broken_quota_store_fails_open_and_logs_once(caplog, monkeypatch):
    def explode():
        raise RuntimeError("redis down")

    # 必须走 monkeypatch：直接 `llm_quota._get_strategy = explode` 会泄漏到后面的用例，
    # 让整条额度闸从此静默 fail-open（实测过：单跑绿、整文件红）。
    monkeypatch.setattr(llm_quota, "_get_strategy", explode)
    set_billing_user("user-A")
    with caplog.at_level(logging.ERROR):
        for _ in range(5):
            charge_if_real_provider(provider="openai")

    assert len([r for r in caplog.records if "fail-open" in r.getMessage()]) == 1


def test_limit_of_zero_disables_the_gate(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CALLS_PER_USER_PER_MINUTE", 0)
    set_billing_user("user-A")
    for _ in range(50):
        charge_if_real_provider(provider="openai")


def test_chat_json_is_refused_before_any_audit_row_is_written(monkeypatch):
    """超额的那一次不能留下"看起来真跑过"的审计行：扣额度在 trace 之前。"""
    set_billing_user("user-A")
    for _ in range(3):  # fixture 给的额度是 3/分钟，先花完
        charge_if_real_provider(provider="openai")

    traced: list[dict] = []
    calls: list[int] = []
    monkeypatch.setattr(llm_service, "LLMTraceScope", SimpleNamespace(begin=lambda **kw: traced.append(kw)))
    monkeypatch.setattr(llm_service, "_openai_compatible_chat", lambda *a, **k: calls.append(1))

    with pytest.raises(LLMQuotaExceededError):
        llm_service.chat_json("超额之后不该发请求")

    assert traced == [], "额度拒绝之前就已经开了 trace scope"
    assert calls == [], "额度拒绝之后还发了 provider 请求"


def test_the_http_layer_turns_it_into_a_429():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/resume/1/diagnose"), method="POST", client=None)
    response = asyncio.run(llm_quota_handler(request, LLMQuotaExceededError("额度用尽")))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 429
    assert "额度" in response.body.decode("utf-8")


def test_get_current_user_is_what_sets_the_identity(db_session):
    """身份只来自这一处（E19 之后每条受守护路由都会经过它），所以不需要在 8 个昂贵路由上加参数。"""
    from app.api.auth import get_current_user
    from app.models.user import User

    user = User(username="quota-user", email="quota-user@x.io", password=hash_password("QuotaPass123!"))
    db_session.add(user)
    db_session.commit()

    llm_quota.reset_for_tests()
    token = create_access_token({"sub": str(user.id)})
    resolved = get_current_user(authorization=f"Bearer {token}", db=db_session)

    assert resolved.id == user.id
    assert llm_quota.billing_key() == f"user:{user.id}"


def test_the_worker_entry_sets_the_identity_too():
    """编排的花费发生在 worker 线程里，而 `logging_utils` 那套上下文是 threading.local ——
    不显式设身份，worker 里的调用就全员不扣。这里在策略创建点读当时的身份。"""
    from app.services import orchestration_runner as runner

    observed: dict[str, object] = {}

    class StubSession:
        def get(self, *_a, **_k):
            return None

        def add(self, *_a):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    def create(name, registry):
        observed["billing_key"] = llm_quota.billing_key()
        observed["strategy"] = name
        return SimpleNamespace(run=lambda *a, **k: {"status": "success"})

    original_factory = runner.StrategyFactory
    original_session = runner.SessionLocal
    try:
        runner.StrategyFactory = SimpleNamespace(create=create)
        runner.SessionLocal = StubSession
        llm_quota.reset_for_tests()
        runner._run_task_payload(runner.TaskPayload("linear", 1, 2, 3, user_id=77, run_id=None))
    finally:
        runner.StrategyFactory = original_factory
        runner.SessionLocal = original_session

    assert observed.get("billing_key") == "user:77", f"worker 线程里没有计费身份：{observed}"
