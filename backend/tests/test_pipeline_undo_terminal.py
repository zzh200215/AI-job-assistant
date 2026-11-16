"""误点的终态可以撤销（D18）。

背景：`VALID_TRANSITIONS` 里终态（已入职 / 已拒绝 / 已放弃）是空集，这是有意的——那三段是
"这件事结束了"。但"点错一下就只能删除重建"是另一个问题：删了记录，阶段历史跟着一起丢。

所以撤销**不是**给状态机加反向边，而是一次单独的操作：只退回最后一次真实转移的 `from_stage`
（凭 `stage_history` 里那一步自己记下的），撤销本身也追加一条历史，不删旧条目。

四条判据：
1. 撤销把阶段退回去，并且历史**变长**（`action: undo`），不是把上一次弹掉；
2. 非终态不许撤销（否则"撤销"就变成任意回退，把状态机绕过去了）；
3. 没有历史的老记录说清"回不去"，不猜一个阶段；
4. 别人的记录动不了。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.job_pipeline import router as pipeline_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.job_pipeline import JobApplicationPipeline
from app.models.user import User


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(pipeline_router, prefix="/jobs")
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    with TestClient(app) as test_client:
        yield test_client


def _user(db, name: str) -> User:
    user = User(username=name, email=f"{name}@example.com", password=hash_password("abc12345"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _entry(db, user: User, stage: str, history: list[dict] | None) -> JobApplicationPipeline:
    entry = JobApplicationPipeline(
        user_id=user.id,
        title="后端工程师",
        company="Test Co",
        stage=stage,
        stage_history=history or [],
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _reached(stage: str, from_stage: str) -> dict:
    return {"stage": stage, "from_stage": from_stage, "at": "2026-11-16T10:00:00"}


def test_undo_returns_to_the_stage_that_was_left_and_appends_history(client, db_session):
    user = _user(db_session, "undo_ok")
    history = [_reached("applied", "todo"), _reached("interview", "applied"), _reached("rejected", "interview")]
    entry = _entry(db_session, user, "rejected", history)

    resp = client.post(f"/jobs/pipeline/{entry.id}/undo-terminal", headers=_headers(user))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stage"] == "interview"
    # 历史变长一条，且明说这是一次撤销——不是把上一次弹掉
    assert len(data["stage_history"]) == len(history) + 1
    assert data["stage_history"][-1]["action"] == "undo"
    assert data["stage_history"][-1]["from_stage"] == "rejected"
    assert data["stage_history"][-1]["stage"] == "interview"
    assert data["stage_history"][1] == history[1]  # 旧条目原样保留

    db_session.refresh(entry)
    assert entry.stage == "interview"


def test_a_non_terminal_stage_cannot_be_undone(client, db_session):
    user = _user(db_session, "undo_open")
    entry = _entry(db_session, user, "interview", [_reached("interview", "applied")])

    resp = client.post(f"/jobs/pipeline/{entry.id}/undo-terminal", headers=_headers(user))

    body = resp.json()
    assert body["code"] != 0
    assert "只有终态" in body["message"]
    db_session.refresh(entry)
    assert entry.stage == "interview"


def test_a_record_without_history_is_told_so_instead_of_guessing(client, db_session):
    user = _user(db_session, "undo_legacy")
    entry = _entry(db_session, user, "accepted", [])

    resp = client.post(f"/jobs/pipeline/{entry.id}/undo-terminal", headers=_headers(user))

    body = resp.json()
    assert body["code"] != 0
    assert "没有可回退的阶段历史" in body["message"]
    db_session.refresh(entry)
    assert entry.stage == "accepted"


def test_another_users_entry_is_not_touchable(client, db_session):
    owner = _user(db_session, "undo_owner")
    other = _user(db_session, "undo_other")
    entry = _entry(db_session, owner, "withdrawn", [_reached("withdrawn", "applied")])

    resp = client.post(f"/jobs/pipeline/{entry.id}/undo-terminal", headers=_headers(other))

    body = resp.json()
    assert body["code"] != 0
    assert "不存在" in body["message"]
    db_session.refresh(entry)
    assert entry.stage == "withdrawn"
