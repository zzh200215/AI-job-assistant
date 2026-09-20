"""M6 外部能力 API 测试（T6-1/2/3）。

T6-1 验收：无 Key → 401；Key 无效 → 401；停用/过期 → 403；超量 → 429；调用写 api_usage。
T6-2 验收：模拟多次调用可生成正确账单；CSV 导出可读。
T6-3 验收：Webhook 订阅 + 投递成功；失败重试后可成功。

使用独立 StaticPool 内存库 + 依赖覆盖，与 conftest 的 db_session 互不干扰。
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_current_user
from app.api.external.router import external_router
from app.core.database import Base, get_db
from app.core.user_roles import ADMIN_ROLE
from app.models.api_key import ApiKey
from app.models.api_usage import ApiUsage
from app.models.organization import Organization
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.services import webhook_service
from app.services.api_key_service import create_api_key, run_monthly_billing
from app.utils.time_helper import utc_now_naive

_admin_user = User(id=1, username="admin", email="admin@example.com", role=ADMIN_ROLE)


@pytest.fixture
def engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=e)
    yield e
    e.dispose()


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine)


def _build_app(factory):
    app = FastAPI()

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: _admin_user
    app.include_router(external_router, prefix="/api")
    return app


def _seed_org(factory, tenant_id: int):
    session = factory()
    try:
        org = session.query(Organization).filter(Organization.id == tenant_id).first()
        if org is None:
            session.add(
                Organization(
                    id=tenant_id,
                    name=f"租户{tenant_id}",
                    slug=f"tenant-{tenant_id}",
                    owner_id=1,
                    status="active",
                )
            )
            session.commit()
    finally:
        session.close()


def _seed_key(factory, *, name="客户A", tenant_id=1, daily_quota=1000, status="active", expires_at=None, revoked=False):
    _seed_org(factory, tenant_id)
    session = factory()
    try:
        key, plain = create_api_key(
            session,
            name=name,
            tenant_id=tenant_id,
            daily_quota=daily_quota,
            expires_at=expires_at,
        )
        if status == "revoked" or revoked:
            key.status = "revoked"
            session.add(key)
            session.commit()
        key_id = key.id
    finally:
        session.close()
    return plain, key_id


# ===== T6-1 鉴权与限流 =====


def test_no_key_returns_401(factory):
    app = _build_app(factory)
    with TestClient(app) as client:
        resp = client.post("/api/v1/external/resume/parse", json={"content": "测试简历"})
    assert resp.status_code == 401


def test_invalid_key_returns_401(factory):
    app = _build_app(factory)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/external/resume/parse",
            json={"content": "测试简历"},
            headers={"X-API-Key": "sk-invalid-token"},
        )
    assert resp.status_code == 401


def test_revoked_key_returns_403(factory):
    plain, _ = _seed_key(factory, status="revoked")
    app = _build_app(factory)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/external/resume/parse",
            json={"content": "测试简历"},
            headers={"X-API-Key": plain},
        )
    assert resp.status_code == 403


def test_expired_key_returns_403(factory):
    past = utc_now_naive() - timedelta(days=1)
    plain, _ = _seed_key(factory, expires_at=past)
    app = _build_app(factory)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/external/resume/parse",
            json={"content": "测试简历"},
            headers={"X-API-Key": plain},
        )
    assert resp.status_code == 403


def test_resume_parse_success_and_usage_recorded(factory):
    plain, key_id = _seed_key(factory)
    app = _build_app(factory)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/external/resume/parse",
            json={"content": "张三，后端工程师，5 年经验，精通 Python", "request_id": "req-001"},
            headers={"X-API-Key": plain},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["request_id"] == "req-001"

    session = factory()
    try:
        rows = session.query(ApiUsage).filter(ApiUsage.api_key_id == key_id).all()
        assert len(rows) == 1
        assert rows[0].endpoint == "resume.parse"
        assert rows[0].status == "success"
        assert int(rows[0].amount) == 30  # ¥0.30
    finally:
        session.close()


def test_daily_quota_exceeded_returns_429(factory):
    plain, _ = _seed_key(factory, daily_quota=2)
    app = _build_app(factory)
    with TestClient(app) as client:
        for _ in range(2):
            resp = client.post(
                "/api/v1/external/match/evaluate",
                json={"resume": {"name": "张三"}, "jd": {"title": "后端工程师"}},
                headers={"X-API-Key": plain},
            )
            assert resp.status_code == 200
        resp = client.post(
            "/api/v1/external/match/evaluate",
            json={"resume": {"name": "张三"}, "jd": {"title": "后端工程师"}},
            headers={"X-API-Key": plain},
        )
    assert resp.status_code == 429


def test_match_and_interview_success(factory):
    plain, _ = _seed_key(factory)
    app = _build_app(factory)
    with TestClient(app) as client:
        r1 = client.post(
            "/api/v1/external/match/evaluate",
            json={"resume": {"skills": ["Python"], "years_exp": 5}, "jd": {"title": "后端工程师"}},
            headers={"X-API-Key": plain},
        )
        r2 = client.post(
            "/api/v1/external/interview/simulate",
            json={
                "resume": {"name": "张三"},
                "jd": {"title": "后端工程师"},
                "answers": [{"question": "请自我介绍", "answer": "我是张三"}],
            },
            headers={"X-API-Key": plain},
        )
    assert r1.status_code == 200 and r1.json()["success"] is True
    assert r2.status_code == 200 and r2.json()["success"] is True
    assert "evaluations" in r2.json()["data"]


def test_interview_simulate_rejects_excessive_answers(factory):
    """answers 超上限应被拒绝（失败不计费），防止 N 次 LLM 调用只记 1 笔账单（#7）。"""
    plain, _ = _seed_key(factory)
    app = _build_app(factory)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/external/interview/simulate",
            json={
                "resume": {"name": "张三"},
                "jd": {"title": "后端工程师"},
                "answers": [{"question": f"q{i}", "answer": "a"} for i in range(21)],
            },
            headers={"X-API-Key": plain},
        )
    assert resp.status_code == 400  # 业务失败不再返回 HTTP 200（契约对齐）
    body = resp.json()
    assert body["success"] is False
    assert "answers" in body["error"]
    session = factory()
    try:
        from app.models.api_usage import ApiUsage

        failed = session.query(ApiUsage).filter(ApiUsage.status == "failed").count()
        assert failed == 1  # 失败调用被记录但不计费
    finally:
        session.close()


# ===== T6-2 计费与账单 =====


def test_billing_generates_correct_amounts(factory):
    plain, key_id = _seed_key(factory, name="计费客户")
    app = _build_app(factory)
    with TestClient(app) as client:
        for _ in range(2):
            client.post(
                "/api/v1/external/resume/parse",
                json={"content": "测试简历"},
                headers={"X-API-Key": plain},
            )
        client.post(
            "/api/v1/external/match/evaluate",
            json={"resume": {"name": "张三"}, "jd": {"title": "后端工程师"}},
            headers={"X-API-Key": plain},
        )

    now = utc_now_naive()
    session = factory()
    try:
        from app.models.api_bill import ApiBill

        bill_ids = run_monthly_billing(session, now.year, now.month)
        bill = session.query(ApiBill).filter(ApiBill.api_key_id == key_id).first()
        assert bill is not None and bill.id in bill_ids
        # 2 次 resume.parse(30) + 1 次 match.evaluate(30) = 90 分
        assert bill.usage_count == 3
        assert int(bill.total_amount) == 90
        line = bill.line_items or {}
        assert line["resume.parse"]["count"] == 2
        assert line["match.evaluate"]["count"] == 1
    finally:
        session.close()


def test_billing_csv_export(factory):
    plain, key_id = _seed_key(factory)
    app = _build_app(factory)
    with TestClient(app) as client:
        client.post(
            "/api/v1/external/resume/parse",
            json={"content": "测试简历"},
            headers={"X-API-Key": plain},
        )
        now = utc_now_naive()
        resp = client.post(
            "/api/v1/admin/external/billing/run",
            json={"year": now.year, "month": now.month},
            headers={"Authorization": "Bearer admin-token"},
        )
        assert resp.status_code == 200
        bill_id = resp.json()["bill_ids"][0]
        csv_resp = client.get(
            f"/api/v1/admin/external/billing/bills/{bill_id}/export",
            headers={"Authorization": "Bearer admin-token"},
        )
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "resume.parse" in csv_resp.text
    assert "合计" in csv_resp.text


def test_admin_key_management(factory):
    _seed_org(factory, 1)
    app = _build_app(factory)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer admin-token"}
        created = client.post(
            "/api/v1/admin/external/api-keys",
            json={"name": "新客户", "tenant_id": 1, "daily_quota": 500},
            headers=headers,
        )
        assert created.status_code == 200
        plain = created.json()["api_key"]
        assert plain.startswith("sk-")

        key_id = created.json()["id"]
        listed = client.get("/api/v1/admin/external/api-keys", headers=headers)
        assert any(item["id"] == key_id for item in listed.json()["items"])

        revoked = client.post(f"/api/v1/admin/external/api-keys/{key_id}/revoke", headers=headers)
        assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"


# ===== T6-3 Webhook =====


def test_webhook_subscribe_and_list(factory):
    _seed_org(factory, 1)
    plain, key_id = _seed_key(factory)
    app = _build_app(factory)
    headers = {"Authorization": "Bearer admin-token"}
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/admin/external/webhooks",
            json={
                "api_key_id": key_id,
                "event": "resume.parsed",
                "url": "https://example.com/hook",
                "secret": "s3cret",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        sub_id = resp.json()["id"]

        listed = client.get(f"/api/v1/admin/external/webhooks?api_key_id={key_id}", headers=headers)
        assert any(item["id"] == sub_id for item in listed.json()["items"])


class _HookHandler(BaseHTTPRequestHandler):
    """记录收到的 POST，可选择首次失败（用于重试测试）。"""

    received = []
    fail_first = False
    call_count = 0

    def do_POST(self):
        type(self).call_count += 1
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).received.append(
            {
                "path": self.path,
                "signature": self.headers.get("X-Webhook-Signature", ""),
                "event": self.headers.get("X-Webhook-Event", ""),
                "webhook_id": self.headers.get("X-Webhook-Id", ""),
                "webhook_timestamp": self.headers.get("X-Webhook-Timestamp", ""),
                "body": body.decode("utf-8"),
            }
        )
        if type(self).fail_first and type(self).call_count == 1:
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _start_hook_server(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}/hook"


def test_webhook_deliver_and_signature(factory):
    _HookHandler.received = []
    _HookHandler.call_count = 0
    _HookHandler.fail_first = False
    server, url = _start_hook_server(_HookHandler)
    try:
        sub = WebhookSubscription(
            api_key_id=1, tenant_id=1, event="resume.parsed", url=url, secret="s3cret", status="active"
        )
        # allow_private=True：本测试把 webhook 投递到 127.0.0.1 本地 HTTP 服务（SSRF 防护之外的测试白名单）
        ok = webhook_service.deliver_webhook(
            sub, {"event": "resume.parsed", "data": {"name": "张三"}}, allow_private=True
        )
        assert ok is True
        assert len(_HookHandler.received) == 1
        received = _HookHandler.received[0]
        assert received["event"] == "resume.parsed"
        assert received["signature"]  # HMAC 签名头存在
        # 验签
        raw = received["body"]
        assert webhook_service.validate_signature("s3cret", raw.encode("utf-8"), received["signature"]) is True
    finally:
        server.shutdown()


def test_webhook_retry_after_failure(factory):
    _HookHandler.received = []
    _HookHandler.call_count = 0
    _HookHandler.fail_first = True
    server, url = _start_hook_server(_HookHandler)
    try:
        sub = WebhookSubscription(
            api_key_id=1, tenant_id=1, event="resume.parsed", url=url, secret="s3cret", status="active"
        )
        # allow_private=True：本测试把 webhook 投递到 127.0.0.1 本地 HTTP 服务（SSRF 防护之外的测试白名单）
        ok = webhook_service.deliver_webhook(sub, {"event": "resume.parsed", "data": {}}, allow_private=True)
        assert ok is True
        assert _HookHandler.call_count >= 2  # 首次 500，重试成功
        assert len(_HookHandler.received) >= 2
    finally:
        server.shutdown()


def test_publish_event_matches_subscriptions(factory):
    _seed_org(factory, 1)
    plain, key_id = _seed_key(factory)
    session = factory()
    try:
        webhook_service.subscribe_webhook(
            session,
            api_key_id=key_id,
            tenant_id=1,
            event="resume.parsed",
            url="http://127.0.0.1:1/nowhere",
            allow_private=True,  # 测试白名单：本用例只验证订阅匹配逻辑，URL 不会真的被投递
        )
        fired = webhook_service.publish_event(
            session, api_key_id=key_id, event="resume.parsed", payload={"name": "张三"}
        )
        # 只匹配 resume.parsed 订阅
        assert fired == 1
        fired_other = webhook_service.publish_event(session, api_key_id=key_id, event="interview.completed", payload={})
        assert fired_other == 0
    finally:
        session.close()


# ===== 中危修复回归：失败计配额 / 月度结算 / SSRF / 防重放 =====


def test_failed_calls_count_toward_daily_quota(factory):
    """失败调用同样消耗资源，应计入日配额，防止无限免费烧 LLM（#17）。"""
    plain, _ = _seed_key(factory, daily_quota=2)
    app = _build_app(factory)
    with TestClient(app) as client:
        headers = {"X-API-Key": plain}
        # 第 1 次成功
        r1 = client.post("/api/v1/external/resume/parse", json={"content": "测试简历"}, headers=headers)
        assert r1.status_code == 200
        # 第 2 次业务失败（answers 超限）→ 仍占 1 个配额
        r2 = client.post(
            "/api/v1/external/interview/simulate",
            json={
                "resume": {"name": "a"},
                "jd": {"title": "b"},
                "answers": [{"question": f"q{i}", "answer": "a"} for i in range(21)],
            },
            headers=headers,
        )
        assert r2.status_code == 400
        # 第 3 次：成功+失败共 2 次 → 额度用尽 → 429
        r3 = client.post("/api/v1/external/resume/parse", json={"content": "测试简历"}, headers=headers)
    assert r3.status_code == 429


def test_monthly_billing_includes_inactive_keys_and_skips_paid(factory):
    """停用 Key 当月用量仍应出账；已支付账单不因重跑被覆盖（#17）。"""
    from app.models.api_bill import ApiBill

    plain, key_id = _seed_key(factory)
    app = _build_app(factory)
    with TestClient(app) as client:
        client.post(
            "/api/v1/external/resume/parse",
            json={"content": "测试简历"},
            headers={"X-API-Key": plain},
        )

    # 调用后停用 Key
    session = factory()
    key = session.get(ApiKey, key_id)
    key.status = "revoked"
    session.commit()
    session.close()

    now = utc_now_naive()
    db = factory()
    try:
        bill_ids = run_monthly_billing(db, now.year, now.month)
        bill = db.query(ApiBill).filter(ApiBill.api_key_id == key_id).first()
        assert bill is not None and bill.id in bill_ids  # 停用 Key 仍出账
        assert int(bill.total_amount) == 30

        bill.status = "paid"
        db.commit()
        bill_id = bill.id

        run_monthly_billing(db, now.year, now.month)  # 重跑一次，验证不覆盖已付账单
        again = db.get(ApiBill, bill_id)
        assert again.status == "paid"  # 已付账单未被重跑覆盖
        assert int(again.total_amount) == 30
    finally:
        db.close()


def test_webhook_subscribe_rejects_private_url(factory):
    """订阅 URL 指向内网/环回地址应被拒绝（SSRF 防护，#17）。"""
    _seed_org(factory, 1)
    app = _build_app(factory)
    headers = {"Authorization": "Bearer admin-token"}
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/admin/external/webhooks",
            json={
                "api_key_id": 1,
                "event": "resume.parsed",
                "url": "http://127.0.0.1:8000/hook",
                "secret": "s",
            },
            headers=headers,
        )
    assert resp.status_code == 400
    assert "内网" in resp.json()["detail"]


def test_webhook_includes_replay_protection_headers(factory):
    """投递应携带唯一 event_id/timestamp（签名 body + 头），供订阅方防重放（#17）。"""
    _HookHandler.received = []
    _HookHandler.call_count = 0
    _HookHandler.fail_first = False
    server, url = _start_hook_server(_HookHandler)
    try:
        sub = WebhookSubscription(
            api_key_id=1, tenant_id=1, event="resume.parsed", url=url, secret="s3cret", status="active"
        )
        ok = webhook_service.deliver_webhook(
            sub, {"event": "resume.parsed", "data": {"name": "张三"}}, allow_private=True
        )
        assert ok is True
        received = _HookHandler.received[0]
        assert received["webhook_id"]  # X-Webhook-Id 存在
        assert received["webhook_timestamp"]  # X-Webhook-Timestamp 存在
        body = json.loads(received["body"])
        assert body["event_id"] == received["webhook_id"]  # event_id 已进签名 body
        assert body["timestamp"] == received["webhook_timestamp"]
    finally:
        server.shutdown()
