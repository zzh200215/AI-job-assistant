"""外部抓取降级时，**为什么降级**必须一路到达候选人眼前（D229）。

2026-10-12 实测：BOSS 直聘那条唯一活着的适配器，纯 HTTP 拿 `{"code":37,"您的环境存在异常"}`，
真浏览器被弹到 `verify.html`。所以这条链在生产里几乎每次都走降级分支——
而降级分支原先的处理是：demo 那一支把 `info_message` 改写成"已展示演示数据"、
payload 又写 `None if is_demo`，于是**原因在两个地方被丢掉**，前端 `SearchPane.vue` 再叠一层
`&& !isDemo` 抑制。候选人只看到"这是演示数据"，永远看不到"因为风控"。

这里钉三条降级契约，外加一条依赖守卫：`beautifulsoup4` 以前既没进 requirements 也没装，
`HAS_BS4=False` 让 `fetch_detail()` 连 socket 都不开就返回 None、`/jd/import-url` 静默失败。
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import job_search as job_search_api
from app.api.job_search import router as job_search_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription
from app.models.user import User
from app.services.job_spider import HAS_BS4, JobItem

# 爬虫内部串：带实现细节，按 D92 那条口径**不许**当用户文案上屏。
RISK_CONTROL_ERROR = "boss search failed: code 37 您的环境存在异常"
# 候选人该看到的那一句（由 API 层组装，不由爬虫出）。
USER_REASON = "外部岗位渠道这次没有返回数据（可能被限流或需要身份验证）"


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(job_search_router, prefix="/jobs")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _user(db_session, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("abc12345"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'username': user.username})}"}


def _search(client, user, keyword="后端"):
    return client.post(
        "/jobs/search-external",
        params={"keyword": keyword, "city": "", "source": "boss", "save": False},
        headers=_headers(user),
    ).json()


def _stub_spider(monkeypatch, jobs, error):
    monkeypatch.setattr(job_search_api.spider, "search", lambda keyword, city, source, page: (jobs, error))
    monkeypatch.setattr(
        job_search_api.spider,
        "demo",
        lambda keyword, city: (
            [
                JobItem(
                    title="演示岗位",
                    company="演示公司",
                    location="北京",
                    salary_range="15k-25k",
                    raw_text="演示 JD",
                    source="_mock",
                )
            ],
            "",
        ),
    )


def test_demo_fallback_still_carries_the_reason(client, db_session, monkeypatch):
    """库里没有可匹配的本地岗位 ⇒ 只能演示数据；这时候**原因必须还在**。"""
    user = _user(db_session, "demo_reader")
    _stub_spider(monkeypatch, [], RISK_CONTROL_ERROR)

    body = _search(client, user)

    assert body["data"]["result_mode"] == "demo_fallback"
    assert body["data"]["is_demo"] is True
    assert body["data"]["error"] == USER_REASON
    assert "演示数据" in body["message"]
    # 另一半：爬虫内部串不许从任何一处漏进响应（message、data、jobs 全都算）
    assert RISK_CONTROL_ERROR not in json.dumps(body, ensure_ascii=False)


def test_local_fallback_carries_the_reason_too(client, db_session, monkeypatch):
    """有本地岗位时降级成本地库：原因同样不许丢。"""
    user = _user(db_session, "local_reader")
    db_session.add(
        JobDescription(
            user_id=user.id,
            title="后端工程师",
            company="真公司",
            location="北京",
            raw_text="后端服务的 JD 正文",
            source="imported",
            is_active=1,
        )
    )
    db_session.commit()
    _stub_spider(monkeypatch, [], RISK_CONTROL_ERROR)

    body = _search(client, user)

    assert body["data"]["result_mode"] == "local_fallback"
    assert body["data"]["error"] == USER_REASON
    assert body["data"]["total"] >= 1
    assert RISK_CONTROL_ERROR not in json.dumps(body, ensure_ascii=False)


def test_successful_external_search_adds_no_error(client, db_session, monkeypatch):
    """反向证据的另一半：真拿到岗位时不许凭空造出一句"失败原因"。"""
    user = _user(db_session, "live_reader")
    _stub_spider(
        monkeypatch,
        [
            JobItem(
                title="后端工程师",
                company="甲方",
                location="上海",
                salary_range="30k-45k",
                raw_text="真实 JD 正文",
                source="boss",
            )
        ],
        None,
    )

    body = _search(client, user)

    assert body["data"]["result_mode"] == "external"
    assert body["data"]["error"] is None
    assert body["data"]["is_demo"] is False


def test_bs4_declared_in_requirements_is_actually_importable():
    """`job_spider` 用 try/except 把 bs4 做成可选，于是"依赖没装"从来不报错、只是少一档能力。

    这条守卫把那种静默变成一次红：谁把 `beautifulsoup4` 从 requirements 里删掉、或者环境里装不上，
    CI 立刻在这里失败，而不是等到有人问"为什么抓详情永远返回失败"。
    """
    assert HAS_BS4 is True, (
        "beautifulsoup4 不可用：HTML 那一档解析与 /jd/import-url 都会静默失效 "
        "（fetch_detail 会在不开 socket 的情况下直接返回 None）。它必须留在 requirements.txt 里。"
    )
