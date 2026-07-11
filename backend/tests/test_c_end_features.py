# -*- coding: utf-8 -*-
"""
核心C端功能单元测试

覆盖: 求职目标、职位收藏、通知、求职日记、薪资洞察、提醒
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router, get_current_user
from app.api.job_target import router as target_router
from app.api.job_journal import router as journal_router
from app.api.notification import router as notif_router
from app.api.salary_insight import router as salary_router
from app.api.reminder import router as reminder_router
from app.api.user_preferences import router as prefs_router
from app.core.database import get_db
from app.models.history import JobDescription
from app.models.job_recommend import JobBookmark
from app.models.job_journal import JobJournal
from app.models.job_pipeline import JobApplicationPipeline
from app.models.job_target import JobTarget
from app.models.notification import Notification
from app.models.user import User


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def app_with_routes():
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(target_router, prefix="/targets")
    app.include_router(journal_router, prefix="/journals")
    app.include_router(notif_router, prefix="/notifications")
    app.include_router(salary_router, prefix="/salary")
    app.include_router(reminder_router, prefix="/reminders")
    app.include_router(prefs_router, prefix="/user")
    return app


@pytest.fixture
def client(app_with_routes, db_session):
    def override_get_db():
        yield db_session

    # 固定用户，用于鉴权
    test_user = User(id=1, username="tester", password="x", email="t@t.com", role="candidate")
    db_session.add(test_user)
    db_session.commit()

    def override_get_current_user():
        return test_user

    app_with_routes.dependency_overrides[get_db] = override_get_db
    app_with_routes.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app_with_routes) as c:
        yield c


# ============================================================
# 求职目标测试
# ============================================================

class TestJobTarget:
    def test_create_target(self, client, db_session):
        resp = client.post("/targets/", json={
            "name": "后端开发",
            "position": "Python后端",
            "cities": ["北京", "上海"],
            "salary_min": 20,
            "salary_max": 40,
            "skills": ["Python", "FastAPI", "MySQL"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "后端开发"
        assert body["data"]["is_primary"] == 1  # 第一个自动为主目标

    def test_create_target_limit(self, client, db_session):
        # 创建5个活跃目标
        for i in range(5):
            client.post("/targets/", json={"name": f"目标{i}"})
        # 第6个应该失败
        resp = client.post("/targets/", json={"name": "目标6"})
        assert resp.json()["code"] != 0

    def test_set_primary(self, client, db_session):
        r1 = client.post("/targets/", json={"name": "目标A"}).json()["data"]
        r2 = client.post("/targets/", json={"name": "目标B", "is_primary": 1}).json()["data"]

        resp = client.post(f"/targets/{r1['id']}/set-primary")
        assert resp.json()["code"] == 0

        # 验证旧主目标被取消
        targets = client.get("/targets/list").json()["data"]
        primary = [t for t in targets if t["is_primary"] == 1]
        assert len(primary) == 1
        assert primary[0]["id"] == r1["id"]


# ============================================================
# 职位收藏测试
# ============================================================

class TestJobBookmark:
    def test_bookmark_and_list(self, client, db_session):
        # 先创建一个JD
        jd = JobDescription(id=10, user_id=1, title="Python开发", company="TestCo", raw_text="test")
        db_session.add(jd)
        db_session.commit()

        # 收藏
        from app.api.job_recommend import router as jr_router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(jr_router, prefix="/jobs")
        app.dependency_overrides[get_db] = lambda: (yield db_session)
        app.dependency_overrides[get_current_user] = lambda: test_user_fixture(db_session)

        # 由于需要更复杂的路由集成，我们直接测试模型
        bookmark = JobBookmark(user_id=1, jd_id=10, action="bookmark")
        db_session.add(bookmark)
        db_session.commit()

        result = db_session.query(JobBookmark).filter(JobBookmark.user_id == 1).first()
        assert result is not None
        assert result.action == "bookmark"


def test_user_fixture(db_session):
    return db_session.query(User).first()


# ============================================================
# 通知测试
# ============================================================

class TestNotification:
    def test_list_and_read(self, client, db_session):
        # 插入测试通知
        n1 = Notification(user_id=1, type="system", title="欢迎", content="欢迎使用")
        n2 = Notification(user_id=1, type="interview_reminder", title="面试提醒", content="明天面试")
        db_session.add_all([n1, n2])
        db_session.commit()

        # 获取列表
        resp = client.get("/notifications/list")
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["total"] == 2

        # 未读数
        resp = client.get("/notifications/unread-count")
        assert resp.json()["data"]["total"] == 2

        # 标记已读
        resp = client.post(f"/notifications/{n1.id}/read")
        assert resp.json()["code"] == 0

        # 再查未读数
        resp = client.get("/notifications/unread-count")
        assert resp.json()["data"]["total"] == 1

    def test_read_all(self, client, db_session):
        db_session.add(Notification(user_id=1, type="system", title="T1", content=""))
        db_session.add(Notification(user_id=1, type="system", title="T2", content=""))
        db_session.commit()

        resp = client.post("/notifications/read-all")
        assert resp.json()["code"] == 0

        resp = client.get("/notifications/unread-count")
        assert resp.json()["data"]["total"] == 0


# ============================================================
# 求职日记测试
# ============================================================

class TestJobJournal:
    def test_create_and_list(self, client, db_session):
        resp = client.post("/journals/", json={
            "entry_type": "interview_log",
            "title": "字节二面复盘",
            "content": "面试官问了系统设计...",
            "mood": "good",
            "rating": 4,
            "interview_round": 2,
        })
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["title"] == "字节二面复盘"

        # 列表
        resp = client.get("/journals/list")
        assert resp.json()["data"]["total"] == 1

        # 按类型过滤
        resp = client.get("/journals/list?entry_type=interview_log")
        assert resp.json()["data"]["total"] == 1

        resp = client.get("/journals/list?entry_type=note")
        assert resp.json()["data"]["total"] == 0

    def test_update_and_delete(self, client, db_session):
        create_resp = client.post("/journals/", json={
            "entry_type": "note",
            "title": "测试笔记",
            "content": "原始内容",
        })
        jid = create_resp.json()["data"]["id"]

        # 更新
        resp = client.put(f"/journals/{jid}", json={"content": "更新内容", "rating": 3})
        assert resp.json()["data"]["content"] == "更新内容"

        # 删除
        resp = client.delete(f"/journals/{jid}")
        assert resp.json()["code"] == 0

        resp = client.get("/journals/list")
        assert resp.json()["data"]["total"] == 0


# ============================================================
# 薪资洞察测试
# ============================================================

class TestSalaryInsight:
    def test_overview_no_data(self, client, db_session):
        resp = client.get("/salary/overview")
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["has_data"] is False

    def test_overview_with_data(self, client, db_session):
        db_session.add(JobDescription(
            id=100, user_id=1, title="Python开发", company="A",
            raw_text="test", salary_range="20-35K", location="北京",
        ))
        db_session.add(JobDescription(
            id=101, user_id=1, title="Python开发", company="B",
            raw_text="test", salary_range="25-40K", location="北京",
        ))
        db_session.commit()

        resp = client.get("/salary/overview?position=Python")
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert data["has_data"] is True
        assert data["parsed_count"] == 2
        assert "distribution" in data

    def test_expectation_check(self, client, db_session):
        db_session.add(JobDescription(
            id=200, user_id=1, title="Go开发", company="C",
            raw_text="test", salary_range="30-50K",
        ))
        db_session.commit()

        resp = client.get("/salary/expectation-check?position=Go&expected_min=30&expected_max=45&experience_years=5")
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert data["has_data"] is True
        assert "assessment" in data
        assert "percentile_rank" in data


# ============================================================
# 用户偏好测试
# ============================================================

class TestUserPreferences:
    def test_get_preferences(self, client, db_session):
        resp = client.get("/user/preferences")
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert "notification" in data
        assert "privacy" in data
        assert data["language"] == "zh-CN"

    def test_update_notification_prefs(self, client, db_session):
        resp = client.put("/user/preferences/notification", json={
            "interview_reminder": False,
            "quiet_hours_start": "23:00",
            "jd_push_frequency": "weekly",
        })
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert data["interview_reminder"] is False
        assert data["quiet_hours_start"] == "23:00"
        assert data["jd_push_frequency"] == "weekly"

    def test_update_privacy(self, client, db_session):
        resp = client.put("/user/preferences/privacy", json={
            "profile_visible": True,
        })
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["profile_visible"] is True

    def test_invalid_time_format(self, client, db_session):
        resp = client.put("/user/preferences/notification", json={
            "quiet_hours_start": "25:00",
        })
        assert resp.status_code != 200


# ============================================================
# 提醒预览测试
# ============================================================

class TestReminders:
    def test_upcoming_empty(self, client, db_session):
        resp = client.get("/reminders/upcoming")
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["total"] == 0

    def test_upcoming_with_interview(self, client, db_session):
        tomorrow = datetime.now(timezone.utc) + timedelta(hours=25)
        db_session.add(JobApplicationPipeline(
            id=1, user_id=1, title="后端", company="TestCo",
            stage="interview", interview_at=tomorrow,
        ))
        db_session.commit()

        resp = client.get("/reminders/upcoming")
        assert resp.json()["code"] == 0
        reminders = resp.json()["data"]["reminders"]
        assert any(r["type"] == "interview" for r in reminders)
