"""Authentication API tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.core.database import get_db


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def register_user(client, **overrides):
    payload = {
        "username": "test_user",
        "email": "test@example.com",
        "password": "StrongP@ssw0rd",
    }
    payload.update(overrides)
    return client.post("/auth/register", json=payload)


class TestAuthApi:
    def test_register_success_normalizes_input(self, client):
        response = register_user(
            client,
            username="  Test_User  ",
            email="  TEST@Example.com  ",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["user"]["username"] == "Test_User"
        assert body["data"]["user"]["email"] == "test@example.com"
        assert body["data"]["user"]["role"] == "candidate"
        assert body["data"]["access_token"]

    def test_register_rejects_duplicate_email_case_insensitive(self, client):
        first = register_user(client, email="first@example.com")
        second = register_user(
            client,
            username="another_user",
            email="FIRST@example.com",
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["code"] != 0
        assert "邮箱" in second.json()["message"]

    def test_register_rejects_weak_password(self, client):
        response = register_user(client, password="weakpass")

        assert response.status_code == 422


class TestAccountDeletion:
    def test_delete_account_removes_user_and_data(self, client, db_session):
        """DELETE /auth/account 应删除用户及其关联数据（#9）。"""
        reg = register_user(client, username="del_user", email="del@example.com")
        assert reg.status_code == 200
        token = reg.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        from app.models.user import User

        user = db_session.query(User).filter(User.username == "del_user").first()
        assert user is not None

        from app.models.history import AnalysisRecord, JobDescription, Resume

        resume = Resume(
            user_id=user.id,
            file_name="r.pdf",
            file_path="uploads/r.pdf",
            file_type="pdf",
            file_size=1,
            parsed_json={"name": "张三"},
            is_deleted=0,
        )
        jd = JobDescription(
            user_id=user.id, title="后端工程师", company="X", raw_text="jd", source="manual", is_active=1
        )
        db_session.add_all([resume, jd])
        db_session.commit()
        db_session.refresh(resume)
        db_session.refresh(jd)
        analysis = AnalysisRecord(
            user_id=user.id,
            resume_id=resume.id,
            jd_id=jd.id,
            match_score=80,
            match_report={},
            optimize_suggestions={},
            interview_questions={},
        )
        db_session.add(analysis)
        db_session.commit()
        # 删除前先缓存主键：bulk delete 后对象在 identity map 中 stale，
        # 此时再访问属性（如 resume.id）会触发刷新并抛 ObjectDeletedError
        user_id, resume_id, analysis_id = user.id, resume.id, analysis.id

        resp = client.delete("/auth/account", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        assert db_session.query(User).filter(User.id == user_id).count() == 0
        assert db_session.query(Resume).filter(Resume.id == resume_id).count() == 0
        assert db_session.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).count() == 0

    def test_login_supports_username(self, client):
        register_user(client, username="login_user", email="login@example.com")
        response = client.post(
            "/auth/login",
            json={"account": "LOGIN_USER", "password": "StrongP@ssw0rd"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["user"]["username"] == "login_user"
        assert body["data"]["user"]["role"] == "candidate"

    def test_login_accepts_legacy_email_field(self, client):
        register_user(client)
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "StrongP@ssw0rd"},
        )

        assert response.status_code == 200
        assert response.json()["code"] == 0

    def test_change_password_requires_current_password(self, client):
        """改密必须凭当前密码。

        这条腿钉的是一次真实的安全修复：原先前端的"修改密码"跳去
        `POST /auth/reset-password`，只收「账号 + 注册邮箱」——两者都是公开信息，
        知道别人用户名与邮箱就能改掉别人的密码。那个端点已删除，改密只剩这条要旧密码的链。
        """
        registered = register_user(client, username="chg_user", email="chg@example.com")
        token = registered.json()["data"]["access_token"]

        wrong_old = client.put(
            "/auth/me/password",
            json={
                "old_password": "WrongP@ssw0rd",
                "new_password": "Newpass123!",
                "confirm_password": "Newpass123!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert wrong_old.json()["code"] != 0
        assert "当前密码" in wrong_old.json()["message"]

        # 旧密码错了就不许改：原来那一个还得能用
        still_old = client.post(
            "/auth/login",
            json={"account": "chg_user", "password": "StrongP@ssw0rd"},
        )
        assert still_old.json()["code"] == 0

        ok_resp = client.put(
            "/auth/me/password",
            json={
                "old_password": "StrongP@ssw0rd",
                "new_password": "Newpass123!",
                "confirm_password": "Newpass123!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok_resp.json()["code"] == 0

        old_login = client.post(
            "/auth/login",
            json={"account": "chg_user", "password": "StrongP@ssw0rd"},
        )
        assert old_login.json()["code"] != 0

        new_login = client.post(
            "/auth/login",
            json={"account": "chg_user", "password": "Newpass123!"},
        )
        assert new_login.json()["code"] == 0

    def test_change_password_requires_login(self, client):
        response = client.put(
            "/auth/me/password",
            json={
                "old_password": "StrongP@ssw0rd",
                "new_password": "Newpass123!",
                "confirm_password": "Newpass123!",
            },
        )
        assert response.status_code == 401

    def test_public_reset_without_token_is_gone(self, client):
        """不带凭据的直改路径已删除。

        原 `POST /auth/reset-password` 只凭「账号 + 注册邮箱」就改密。留着它，
        上面那条验旧密码的链等于白做——绕过去就行。所以这里是"路由不存在"，
        不是"路由存在但拒绝"。
        """
        register_user(client, username="gone_user", email="gone@example.com")
        response = client.post(
            "/auth/reset-password",
            json={
                "account": "gone_user",
                "email": "gone@example.com",
                "new_password": "Newpass123!",
                "confirm_password": "Newpass123!",
            },
        )
        assert response.status_code in (404, 405)

    def test_forgot_password_then_reset_with_token(self, client):
        """忘记密码走 token 链，且新密码要过注册同一套策略。"""
        register_user(client, username="forgot_user", email="forgot@example.com")

        forgot = client.post("/auth/forgot-password", json={"email": "forgot@example.com"})
        token = forgot.json()["data"]["token"]

        weak = client.post(
            "/auth/reset-password-with-token",
            json={"token": token, "new_password": "weakpass", "confirm_password": "weakpass"},
        )
        assert weak.status_code == 422  # 密码策略由 schema 拦，比原先的"至少 6 位"严

        ok_resp = client.post(
            "/auth/reset-password-with-token",
            json={"token": token, "new_password": "Newpass123!", "confirm_password": "Newpass123!"},
        )
        assert ok_resp.json()["code"] == 0

        new_login = client.post(
            "/auth/login",
            json={"account": "forgot_user", "password": "Newpass123!"},
        )
        assert new_login.json()["code"] == 0

    def test_reset_with_bad_token_rejected(self, client):
        response = client.post(
            "/auth/reset-password-with-token",
            json={"token": "not-a-token", "new_password": "Newpass123!", "confirm_password": "Newpass123!"},
        )
        assert response.json()["code"] != 0

    def test_get_me_requires_valid_token(self, client):
        register_response = register_user(client, username="me_user", email="me@example.com")
        token = register_response.json()["data"]["access_token"]

        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["email"] == "me@example.com"
        assert body["data"]["role"] == "candidate"
        assert body["data"]["is_admin"] is False

    def test_register_rejects_reserved_admin_username(self, client):
        response = register_user(client, username="admin", email="admin@example.com")

        assert response.status_code == 200
        assert response.json()["code"] != 0

    def test_get_me_returns_is_admin_flag_for_seeded_admin(self, client, db_session):
        from app.core.security import hash_password
        from app.models.user import User

        admin = User(
            username="admin",
            email="real_admin@example.com",
            password=hash_password("StrongP@ssw0rd"),
            role="candidate",
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)

        login = client.post(
            "/auth/login",
            json={"account": "admin", "password": "StrongP@ssw0rd"},
        )

        assert login.status_code == 200
        body = login.json()
        assert body["code"] == 0
        assert body["data"]["user"]["is_admin"] is True

    def test_get_me_rejects_invalid_token(self, client):
        response = client.get("/auth/me", headers={"Authorization": "Bearer invalid"})

        assert response.status_code == 401
