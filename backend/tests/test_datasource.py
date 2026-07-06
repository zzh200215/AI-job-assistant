# -*- coding: utf-8 -*-
"""岗位数据源模块测试用例"""
import json
import tempfile
import os
import pytest
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.job_data_source import router as datasource_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.job_data_source import JobDataSource, JobSyncLog
from app.models.user import User
from app.utils.response import ERR_PARAM
from app.services.job_data_source import (
    CsvJobSource, JsonJobSource, MockJobSource, ApiJobSource, ArbeitnowJobSource,
    SyncService, create_adapter,
)
from app.services.job_data_source.adapter import SourceRow


# ==================== Adapter 单元测试 ====================

class TestCsvJobSource:
    def test_read_csv(self):
        content = "title,company,location,salary\nPython工程师,字节,北京,25K\n前端工程师,腾讯,深圳,30K"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(content)
            path = f.name
        try:
            src = CsvJobSource({"file_path": path, "delimiter": ",", "field_mapping": {
                "title": "title", "company": "company", "location": "location", "salary_range": "salary"
            }})
            assert src.connect() is True
            rows = src.read()
            assert len(rows) == 2
            assert rows[0].title == "Python工程师"
            assert rows[0].company == "字节"
        finally:
            os.unlink(path)

    def test_connect_fail(self):
        src = CsvJobSource({"file_path": "/not/exist.csv"})
        assert src.connect() is False


class TestJsonJobSource:
    def test_read_json(self):
        data = {
            "data": {
                "jobs": [
                    {"title": "算法工程师", "company": "阿里", "location": "杭州", "salary": "40K"}
                ]
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            src = JsonJobSource({"file_path": path, "json_path": "data.jobs", "field_mapping": {
                "title": "title", "company": "company", "location": "location", "salary_range": "salary"
            }})
            assert src.connect() is True
            rows = src.read()
            assert len(rows) == 1
            assert rows[0].title == "算法工程师"
        finally:
            os.unlink(path)


class TestMockJobSource:
    def test_read_mock(self):
        src = MockJobSource({})
        assert src.connect() is True
        rows = src.read(limit=2)
        assert len(rows) == 2
        assert rows[0].title != ""


class TestApiJobSource:
    def test_read_api_with_bearer_and_pagination(self, monkeypatch):
        calls = []

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        def fake_get(url, headers=None, params=None, timeout=0):
            calls.append({"url": url, "headers": headers or {}, "params": params or {}, "timeout": timeout})
            page = int((params or {}).get("page", 1))
            if page == 1:
                return FakeResponse({
                    "data": {
                        "jobs": [
                            {"id": "j1", "title": "后端工程师", "company": "A公司", "description": "Python FastAPI"},
                            {"id": "j2", "title": "前端工程师", "company": "B公司", "description": "Vue React"},
                        ],
                        "has_more": True,
                    }
                })
            return FakeResponse({
                "data": {
                    "jobs": [
                        {"id": "j3", "title": "算法工程师", "company": "C公司", "description": "NLP LLM"},
                    ],
                    "has_more": False,
                }
            })

        monkeypatch.setattr("requests.get", fake_get)
        sleep_calls = []
        monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

        src = ApiJobSource({
            "api_url": "https://api.example.com/jobs",
            "api_method": "GET",
            "auth_type": "bearer",
            "auth_token": "token-123",
            "api_query": {"keyword": "python"},
            "json_path": "data.jobs",
            "pagination_enabled": True,
            "page_param": "page",
            "page_start": 1,
            "page_size_param": "page_size",
            "page_size": 2,
            "max_pages": 3,
            "has_more_path": "data.has_more",
            "rate_limit_ms": 200,
            "field_mapping": {
                "title": "title",
                "company": "company",
                "raw_text": "description",
            },
        })

        assert src.connect() is True
        rows = src.read()
        assert len(rows) == 3
        assert rows[0].title == "后端工程师"
        assert rows[2].company == "C公司"
        assert calls[0]["headers"]["Authorization"] == "Bearer token-123"
        assert calls[1]["params"]["page"] == 1
        assert calls[2]["params"]["page"] == 2
        assert sleep_calls == [0.2]

    def test_refresh_token_on_unauthorized(self, monkeypatch):
        calls = []

        class FakeResponse:
            def __init__(self, payload=None, status_code=200):
                self.payload = payload or {}
                self.status_code = status_code

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")

            def json(self):
                return self.payload

        def fake_get(url, headers=None, params=None, timeout=0):
            calls.append(("get", url, dict(headers or {})))
            if len(calls) == 1:
                return FakeResponse(status_code=401)
            return FakeResponse({
                "data": {
                    "jobs": [{"id": "j1", "title": "后端工程师", "company": "A公司"}],
                }
            })

        def fake_post(url, headers=None, params=None, json=None, timeout=0):
            calls.append(("post", url, dict(headers or {})))
            if "refresh" in url:
                return FakeResponse({"data": {"access_token": "new-token"}})
            return FakeResponse(status_code=200)

        monkeypatch.setattr("requests.get", fake_get)
        monkeypatch.setattr("requests.post", fake_post)

        src = ApiJobSource({
            "api_url": "https://api.example.com/jobs",
            "api_method": "GET",
            "auth_type": "bearer",
            "auth_token": "old-token",
            "auth_refresh_url": "https://api.example.com/refresh",
            "auth_refresh_method": "POST",
            "auth_refresh_token_path": "data.access_token",
            "field_mapping": {"title": "title", "company": "company"},
            "retry_max_attempts": 2,
            "retry_backoff_ms": 0,
        })

        rows = src.read()
        assert len(rows) == 1
        assert src.config["auth_token"] == "new-token"
        assert any(call[0] == "post" and call[1].endswith("/refresh") for call in calls)

    def test_retry_on_server_error(self, monkeypatch):
        calls = []

        class FakeResponse:
            def __init__(self, payload=None, status_code=200):
                self.payload = payload or {}
                self.status_code = status_code

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")

            def json(self):
                return self.payload

        def fake_get(url, headers=None, params=None, timeout=0):
            calls.append(1)
            if len(calls) < 2:
                return FakeResponse(status_code=500)
            return FakeResponse({
                "data": {
                    "jobs": [{"id": "j1", "title": "算法工程师", "company": "C公司"}],
                }
            })

        monkeypatch.setattr("requests.get", fake_get)

        src = ApiJobSource({
            "api_url": "https://api.example.com/jobs",
            "api_method": "GET",
            "field_mapping": {"title": "title", "company": "company"},
            "retry_max_attempts": 2,
            "retry_backoff_ms": 0,
        })

        rows = src.read()
        assert len(rows) == 1
        assert len(calls) == 2


class TestArbeitnowJobSource:
    def test_read_arbeitnow(self, monkeypatch):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse({
            "data": [
                {
                    "slug": "python-dev",
                    "title": "Python Developer",
                    "company_name": "ACME",
                    "location": "Remote",
                    "description": "<p>Build APIs</p>",
                    "tags": ["Python", "FastAPI"],
                    "url": "https://arbeitnow.com/job/python-dev",
                }
            ],
            "links": {},
        }))

        src = ArbeitnowJobSource({
            "search_query": "python",
            "field_mapping": {
                "title": "title",
                "company": "company_name",
                "location": "location",
                "raw_text": "description",
                "skill_tags": "tags",
                "external_url": "url",
            },
        })

        assert src.connect() is True
        rows = src.read()
        assert len(rows) == 1
        assert rows[0].title == "Python Developer"
        assert rows[0].company == "ACME"
        assert rows[0].raw_text


class TestAdapterFactory:
    def test_create_adapter(self):
        assert isinstance(create_adapter("csv", {}), CsvJobSource)
        assert isinstance(create_adapter("json", {}), JsonJobSource)
        assert isinstance(create_adapter("mock", {}), MockJobSource)
        assert isinstance(create_adapter("api", {}), ApiJobSource)
        assert isinstance(create_adapter("arbeitnow", {}), ArbeitnowJobSource)
        with pytest.raises(ValueError):
            create_adapter("unknown", {})


# ==================== SourceRow 测试 ====================

class TestSourceRow:
    def test_map_fields(self):
        raw = {"职位": "后端", "公司": "美团", "城市": "上海"}
        adapter = CsvJobSource({"field_mapping": {
            "title": "职位", "company": "公司", "location": "城市"
        }})
        mapped = adapter._map_fields(raw)
        assert mapped["title"] == "后端"
        assert mapped["company"] == "美团"


# ==================== SyncService 集成测试（需 DB） ====================

# 注：以下测试需要依赖注入数据库 Session，建议在 conftest.py 中配置测试 DB
# 此处仅提供骨架，实际运行需结合项目测试环境


@pytest.fixture
def datasource_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(datasource_router, prefix="/datasource")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_recruiter(db_session, username: str, email: str) -> User:
    user = _create_user(db_session, username, email)
    user.role = "recruiter"
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _create_datasource(db_session, *, user_id: int, name: str = "测试数据源", source_type: str = "mock") -> JobDataSource:
    ds = JobDataSource(
        user_id=user_id,
        name=name,
        source_type=source_type,
        config={},
        sync_interval=0,
        status=1,
    )
    db_session.add(ds)
    db_session.commit()
    db_session.refresh(ds)
    return ds


def _create_sync_log(db_session, *, source_id: int, user_id: int) -> JobSyncLog:
    log = JobSyncLog(
        source_id=source_id,
        user_id=user_id,
        status="success",
        total_count=2,
        success_count=2,
        fail_count=0,
        duplicate_count=0,
        embed_count=0,
        duration_ms=10,
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log

class TestSyncService:
    def test_get_existing_external_ids(self, db_session):
        """测试去重逻辑：基于 JobImportBatch 的历史记录"""
        # 需要在 conftest 中提供 db_session fixture
        svc = SyncService(db_session, user_id=1)
        ids = svc._get_existing_external_ids(source_id=1)
        assert isinstance(ids, set)

    def test_save_jd(self, db_session):
        """测试 SourceRow -> tb_jd 写入"""
        svc = SyncService(db_session, user_id=1)
        row = SourceRow(
            external_id="test-1",
            title="测试岗位",
            company="测试公司",
            raw_text="负责测试开发",
            skill_tags=["Python", "pytest"],
        )
        jd = svc._save_jd(row)
        assert jd.id is not None
        assert jd.title == "测试岗位"
        assert jd.source == "imported"


def test_datasource_create_requires_recruiter_role(datasource_client, db_session):
    candidate = _create_user(db_session, "ds_candidate", "ds_candidate@example.com")

    resp = datasource_client.post(
        "/datasource",
        headers=_auth_headers(candidate),
        json={
            "name": "候选人数据源",
            "source_type": "mock",
            "config": {},
            "sync_interval": 0,
        },
    )

    assert resp.status_code == 403


def test_datasource_list_returns_recruiter_owned_sources(datasource_client, db_session):
    recruiter = _create_recruiter(db_session, "ds_owner", "ds_owner@example.com")
    other = _create_recruiter(db_session, "ds_other", "ds_other@example.com")
    own = _create_datasource(db_session, user_id=recruiter.id, name="我的数据源")
    _create_datasource(db_session, user_id=other.id, name="别人的数据源")

    resp = datasource_client.get(
        "/datasource",
        headers=_auth_headers(recruiter),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == own.id
    assert data[0]["name"] == "我的数据源"


def test_datasource_logs_require_recruiter_role(datasource_client, db_session):
    recruiter = _create_recruiter(db_session, "ds_logs_owner", "ds_logs_owner@example.com")
    candidate = _create_user(db_session, "ds_logs_candidate", "ds_logs_candidate@example.com")
    ds = _create_datasource(db_session, user_id=recruiter.id, name="日志数据源")
    _create_sync_log(db_session, source_id=ds.id, user_id=recruiter.id)

    resp = datasource_client.get(
        f"/datasource/{ds.id}/logs",
        headers=_auth_headers(candidate),
    )

    assert resp.status_code == 403


def test_datasource_sync_rejects_foreign_source(datasource_client, db_session):
    recruiter = _create_recruiter(db_session, "ds_sync_owner", "ds_sync_owner@example.com")
    other = _create_recruiter(db_session, "ds_sync_other", "ds_sync_other@example.com")
    foreign = _create_datasource(db_session, user_id=other.id, name="外部数据源")

    resp = datasource_client.post(
        f"/datasource/{foreign.id}/sync",
        headers=_auth_headers(recruiter),
        json={"dry_run": True, "limit": 1},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == ERR_PARAM


# ==================== 端到端 API 测试（可选） ====================

# 使用 TestClient 测试 FastAPI 路由
# from fastapi.testclient import TestClient
# from main import app
#
# client = TestClient(app)
#
# def test_create_datasource_api():
#     resp = client.post("/api/datasource", json={
#         "name": "测试CSV",
#         "source_type": "mock",
#         "config": {},
#         "sync_interval": 0,
#     })
#     assert resp.status_code == 200
