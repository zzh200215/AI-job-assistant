"""§10.25 拍的那条 ①：`GET /interview/performance` 给出**最高一次**面试综合评分。

Profile 的「面试之星 · 综合评分达到85」读的就是这个值，而在这条决定之前全仓没有任何 max 生产者
（最接近的是同返回里的 `avg_overall_score`，是均值）。三条断言各管一件事：

1. 三场面试按 62 / 88 / 71 灌进去，均值 73.7 与最高 88 在**成就线**两侧判定**相反**，
   所以断言 `max_overall_score == 88` 顺带就是"这里给的不是均值"的对照。线本身在 §10.5 从 80
   挪到顶档 85（`utils/scoreTone.js` 的 `INTERVIEW_SCORE_BANDS` 首条），这里的常数跟着那条线走：
   夹具在 80 与 85 两侧都还判得开，所以换了数仍然咬得住"用均值会把达成过的人判成没达成"；
2. 有会话但没有评分时给 0，不炸（成就保持未解锁）；
3. 零场面试那一支走的是提前返回，`max_overall_score` 与 `avg_overall_score` 两个键**都不出现**——
   这一条记的是前端的 `|| 0` 依赖的形状，不是主张。键从有到无会让读方拿到 undefined，
   所以这个形状也得有人钉。
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.interview_rest import interview_performance
from app.core.database import Base
from app.core.tenant_context import reset_tenant_session_factory, set_tenant_session_factory
from app.core.user_roles import CANDIDATE_ROLE
from app.models.interview_session import InterviewSession
from app.models.user import User


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    set_tenant_session_factory(factory)
    yield factory
    reset_tenant_session_factory()
    engine.dispose()


def _seed_candidate(factory):
    db = factory()
    user = User(username="c1", password="x", role=CANDIDATE_ROLE)
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user


def _add_completed_session(db, user, overall_score):
    db.add(
        InterviewSession(
            user_id=user.id,
            tenant_id=1,
            status="completed",
            interview_type="tech",
            evaluation={"overall_score": overall_score},
            completed_at=datetime(2026, 9, 1),
        )
    )
    db.commit()


async def _performance(db, user):
    body = await interview_performance(db=db, current_user=user)
    assert body["code"] == 0, body
    return body["data"]


def test_max_overall_score_is_the_best_session_not_the_average(db_factory):
    db, user = _seed_candidate(db_factory)
    for score in (62, 88, 71):
        _add_completed_session(db, user, score)

    data = asyncio.run(_performance(db, user))

    assert data["max_overall_score"] == 88
    assert data["avg_overall_score"] == 73.7
    # 这一对就是那条 ① 与"改用均值"那条路的分界：成就线（§10.5 起为 85）上两者判定相反。
    assert data["avg_overall_score"] < 85 <= data["max_overall_score"]
    assert data["total_sessions"] == 3


def test_sessions_without_any_score_report_zero_not_a_crash(db_factory):
    db, user = _seed_candidate(db_factory)
    for _ in range(2):
        _add_completed_session(db, user, 0)

    data = asyncio.run(_performance(db, user))

    assert data["max_overall_score"] == 0
    assert data["avg_overall_score"] == 0


def test_no_sessions_at_all_keeps_the_early_return_shape(db_factory):
    """提前返回那一支没有这两个键（`interview_rest.py:758-766`），前端靠 `|| 0` 兜住。
    如果哪天有人把键补成 0，这条会红——那是**载荷形状的变更**，得连带看读方。"""
    db, user = _seed_candidate(db_factory)

    data = asyncio.run(_performance(db, user))

    assert data["total_sessions"] == 0
    assert "max_overall_score" not in data
    assert "avg_overall_score" not in data
