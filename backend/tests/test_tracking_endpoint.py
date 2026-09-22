"""埋点上报端点此前从未挂进 api_router：前端 utils/tracker.js 每 30 秒往
/api/tracking/events 发一批，全部 404。这组测试锁三件事——路由表里真的有它、
带凭据真的收、匿名真的拒（401 而不是 404，否则又回到"看起来没有这个接口"）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.api.router import api_router
from app.api.tracking import router as tracking_router
from app.core.database import get_db
from app.core.security import create_access_token


def _paths(router) -> list[tuple[str, str]]:
    out = []
    for route in router.routes:
        for method in sorted(getattr(route, "methods", set()) or []):
            out.append((method, route.path))
    return out


@pytest.fixture
def client(db_session, override_db, normal_user):
    app = FastAPI()
    app.include_router(tracking_router, prefix="/tracking")
    app.dependency_overrides[get_db] = override_db
    # get_current_user 在真实应用里由请求头驱动；这里给出测试用户即可
    app.dependency_overrides[get_current_user] = lambda: normal_user
    with TestClient(app) as test_client:
        yield test_client


def test_the_real_router_exposes_the_tracking_endpoint():
    """这条在修复前是红的：tracking.router 定义了却没被 include。"""
    assert len(_paths(api_router)) > 200, "遍历失效：真实路由表不该只有这么几条"
    assert ("POST", "/tracking/events") in _paths(api_router)


def test_authenticated_batch_is_accepted(client, normal_user):
    token = create_access_token({"sub": str(normal_user.id), "username": normal_user.username})
    resp = client.post(
        "/tracking/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "events": [
                {"event": "upload_resume", "properties": {"file_type": "pdf"}, "timestamp": "2026-09-22T10:00:00"},
                {"event": "apply_job", "properties": {"jd_id": 12}},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["received"] == 2


def test_anonymous_call_is_rejected_not_missing(db_session, override_db):
    """401 才对：404 意味着这个接口对调用方根本不存在。"""
    app = FastAPI()
    app.include_router(tracking_router, prefix="/tracking")
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as anon:
        resp = anon.post("/tracking/events", json={"events": []})
    assert resp.status_code in (401, 403), f"匿名调用得到 {resp.status_code}；公开面清单见 test_public_api_surface"
