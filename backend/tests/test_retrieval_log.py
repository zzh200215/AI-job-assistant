"""C3 — `retrieval_log` 的写端与读端。

计划原文说这两张表"从未被插入"，实测是错的：dev 库里 `retrieval_log` 有 25 行、
`self_check_log` 有 15 行，全部产于 2026-06-06~07，之后没有一行——和 `agent_message`
一样，写端在同一次"策略化"重构里被弄丢了，`/api/agent/task/{id}/steps` 的两个字段
因此一直是空数组。现在写端住在节点入口里：检索发生在 `rag_service` / `multi_recall`
内部，agent 只拿到一段上下文，所以由真正发查询的函数记，才能把"查了但 0 命中"也留下。
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.base_agent import BaseAgent
from app.api.agent import router as agent_router
from app.api.analysis import _rag_confidence_from_retrievals
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.agent import AgentTask, RetrievalLog, SelfCheckLog
from app.orchestration.context import AgentContext
from app.services import rag_service, retrieval_log


class _Retriever(BaseAgent):
    """节点内做一次（或若干次）知识库读取的假 agent。"""

    name = "RetrieverAgent"
    result_type = "retrieve"
    calls = 1

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        for index in range(self.calls):
            retrieval_log.record(
                query=f"查询 {index}",
                doc_type="skill_model",
                top_k=3,
                results=[{"chunk_id": f"c{index}", "doc_type": "skill_model", "text": "内容", "score": 0.2}],
                duration_ms=12,
            )
        return {"ok": True}


class _FlakyRetriever(BaseAgent):
    """每次都先查一次再失败一次：第三次尝试才成功——前两次的取证都该留下。"""

    name = "FlakyRetrieverAgent"
    result_type = "retrieve"

    def __init__(self, db=None):
        super().__init__(db=db)
        self.attempts = 0

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        self.attempts += 1
        retrieval_log.record(
            query=f"尝试 {self.attempts}",
            doc_type=None,
            top_k=2,
            results=[],
            duration_ms=7,
        )
        if self.attempts < 3:
            raise RuntimeError("瞬时故障")
        return {"attempts": self.attempts}


@pytest.fixture(autouse=True)
def _clean_collector():
    retrieval_log.finish()
    yield
    retrieval_log.finish()


@pytest.fixture
def task_row(db_session) -> AgentTask:
    task = AgentTask(user_id=1, resume_id=1, jd_id=1, status="running")
    db_session.add(task)
    db_session.commit()
    return task


# ===================== 收集器 =====================


def test_record_is_a_noop_outside_a_node():
    """知识库页自己的搜索、外部 API 的检索，不该被记成某次编排的取证。"""
    retrieval_log.record(query="q", doc_type=None, top_k=3, results=[{"chunk_id": "x"}], duration_ms=1)

    assert retrieval_log.finish() == []


def test_search_knowledge_records_every_call(db_session, monkeypatch):
    """一条 search_knowledge = 一行取证，字段来自真实调用参数。"""

    class _Collection:
        def count(self) -> int:
            return 10

        def query(self, **kwargs) -> dict:
            return {
                "ids": [["c1", "c2"]],
                "documents": [["甲", "乙"]],
                "metadatas": [
                    [
                        {"doc_id": "7", "doc_title": "技能模型", "doc_type": "skill_model"},
                        {"doc_id": "7", "doc_title": "技能模型", "doc_type": "skill_model"},
                    ]
                ],
                "distances": [[0.2, 0.4]],
            }

    monkeypatch.setattr(rag_service, "get_knowledge_collection", lambda: _Collection())
    monkeypatch.setattr(rag_service, "get_visible_knowledge_doc_ids", lambda *a, **k: {"7"})
    retrieval_log.begin()

    hits = rag_service.search_knowledge("后端技能要求", doc_type="skill_model", top_k=2, db=db_session, user_id=1)

    assert len(hits) == 2
    calls = retrieval_log.finish()
    assert len(calls) == 1
    assert calls[0]["query_text"] == "后端技能要求"
    assert calls[0]["doc_type_filter"] == "skill_model"
    assert calls[0]["result_count"] == 2
    assert calls[0]["top_k"] == 2
    assert calls[0]["results"][0]["chunk_id"] == "c1"


def test_zero_hit_retrieval_is_still_recorded(db_session, monkeypatch):
    """0 命中也是结论：visible 集为空时同样留行。"""
    monkeypatch.setattr(rag_service, "get_visible_knowledge_doc_ids", lambda *a, **k: set())

    class _Collection:
        def count(self) -> int:
            return 10

    monkeypatch.setattr(rag_service, "get_knowledge_collection", lambda: _Collection())
    retrieval_log.begin()

    assert rag_service.search_knowledge("查不到的东西", db=db_session, user_id=1) == []

    calls = retrieval_log.finish()
    assert len(calls) == 1 and calls[0]["result_count"] == 0


def test_tracked_calls_are_capped_per_node(monkeypatch):
    """一次节点最多留这么多条，日志不该变成语料库的副本。"""
    retrieval_log.begin()
    for index in range(retrieval_log.MAX_TRACKED_PER_NODE + 5):
        retrieval_log.record(query=f"q{index}", doc_type=None, top_k=1, results=[], duration_ms=1)

    assert len(retrieval_log.finish()) == retrieval_log.MAX_TRACKED_PER_NODE


# ===================== 节点落库 =====================


def test_node_persists_retrieval_rows(db_session, task_row):
    _Retriever.calls = 3
    context = AgentContext.for_analysis(1, 1, user_id=1, db=db_session, task_id=task_row.id, run_id=None)

    outcome = _Retriever(db=db_session).execute(0, context)

    rows = db_session.query(RetrievalLog).filter_by(task_id=task_row.id).all()
    assert outcome.succeeded
    assert [r.query_text for r in rows] == ["查询 0", "查询 1", "查询 2"]
    assert {r.doc_type_filter for r in rows} == {"skill_model"}
    assert all(r.result_count == 1 and r.duration_ms == 12 for r in rows)


def test_retried_attempt_keeps_its_retrieval_evidence(db_session, task_row, monkeypatch):
    """重试前那两次也查过知识库——证据不能只剩最后一次。"""
    monkeypatch.setattr("app.agents.base_agent.RETRY_BACKOFF_SECONDS", 0)
    context = AgentContext.for_analysis(1, 1, user_id=1, db=db_session, task_id=task_row.id)

    outcome = _FlakyRetriever(db=db_session).execute(0, context)

    assert outcome.succeeded and outcome.attempts == 3
    rows = db_session.query(RetrievalLog).filter_by(task_id=task_row.id).all()
    assert [r.query_text for r in rows] == ["尝试 1", "尝试 2", "尝试 3"]
    assert all(r.result_count == 0 for r in rows), "0 命中的取证同样落行"


def test_rows_are_skipped_without_a_task(db_session):
    """不在编排里跑（无 task 归属）时不写行。"""
    context = AgentContext.for_analysis(1, 1, user_id=1, db=db_session)

    _Retriever(db=db_session).execute(0, context)

    assert db_session.query(RetrievalLog).count() == 0


# ===================== 读端 =====================


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(agent_router, prefix="/agent")

    def override_get_db():
        yield db_session

    def fake_user():
        from app.models.user import User

        user = db_session.query(User).first()
        if user is None:
            user = User(username="reader", email="reader@example.com", password="x")
            db_session.add(user)
            db_session.commit()
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = fake_user
    with TestClient(app) as test_client:
        yield test_client


def test_steps_endpoint_returns_retrieval_evidence(client, db_session, task_row):
    """`/api/agent/task/{id}/steps` 的 retrievals 不再是恒空数组。"""
    db_session.add(
        RetrievalLog(
            task_id=task_row.id,
            query_text="Python 后端 技能模型",
            doc_type_filter="skill_model",
            top_k=3,
            result_count=1,
            results=[{"chunk_id": "c1", "doc_type": "skill_model", "doc_title": "技能模型", "score": 0.2}],
            duration_ms=30,
        )
    )
    db_session.commit()

    body = client.get(f"/agent/task/{task_row.id}/steps").json()["data"]

    assert len(body["retrievals"]) == 1
    row = body["retrievals"][0]
    assert row["query_text"] == "Python 后端 技能模型"
    assert row["result_count"] == 1
    assert row["results"][0]["chunk_id"] == "c1"


def test_confidence_is_derived_from_logged_retrievals(db_session, task_row):
    """分析详情的 RAG 置信度改为按真实取证计算，复用同一个实现。"""
    db_session.add(
        RetrievalLog(
            task_id=task_row.id,
            query_text="后端工程师 技能",
            doc_type_filter="skill_model",
            top_k=3,
            result_count=2,
            results=[
                {"chunk_id": "a", "doc_type": "skill_model", "doc_title": "技能模型", "score": 0.21},
                {"chunk_id": "b", "doc_type": "skill_model", "doc_title": "技能模型", "score": 0.35},
            ],
            duration_ms=20,
        )
    )
    db_session.commit()

    confidence = _rag_confidence_from_retrievals(db_session, task_row.id)

    assert confidence["signals"]["total_chunks"] == 2
    assert confidence["level"] in {"high", "medium", "low"}
    assert confidence["signals"]["doc_type_counts"]["skill_model"] == 2


def test_confidence_stays_empty_when_nothing_was_retrieved(db_session, task_row):
    """没查过就是没查过，不给一个看起来像结论的默认值。"""
    assert _rag_confidence_from_retrievals(db_session, task_row.id) == {}


def test_self_check_log_still_has_no_writer(db_session, task_row):
    """自检表刻意仍然没有写端。

    唯一现成的"自检"是 SummaryAgent 自己给的 `quality_assurance.self_check_score`——
    模型给自己的报告打分，没有核验方、也没有通过线。把它塞进 `self_check_log.passed`
    就是给意见盖上测量的章（A3 刚清掉六处同类）。等真有独立校验再写，读端返回 [] 是对的。
    """
    assert db_session.query(SelfCheckLog).count() == 0
