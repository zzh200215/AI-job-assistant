"""D281 存量半径：口径要能分清"已有 canonical / 旧形状会多贴 / 旧形状仍对不上"，且脚本真的只读。

这张表唯一的用途是决定"历史规划要不要回填 canonical"，所以每条判据都对着一个会让表安静地
给出错误半径的写法：把空缺口算进旧形状、把'现在按拼写已经对上'也算成回填收益、或漏读
SummaryAgent 里嵌套的那份 career_planning。
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

import scripts.career_gap_canonical_radius as radius
from app.models.agent import AgentStepLog, AgentTask
from app.models.history import AnalysisRecord
from app.models.interview_session import InterviewSession


def _interview(db, user_id: int, skill: str = "Kubernetes", score: int = 50):
    row = InterviewSession(
        user_id=user_id,
        tenant_id=1,
        interview_type="tech",
        status="completed",
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 1),
        evaluation={
            "overall_score": 62,
            "dimension_scores": {"completeness": 80, "accuracy": 75, "depth": 58, "expression": 60},
            "question_evaluations": [
                {
                    "question": f"{skill} 的调度怎么做的？",
                    "overall_score": score,
                    "feedback": "只说了概念",
                }
            ],
            "answered_questions": 1,
            "interview_memory": {"jd_required_skills": [skill]},
        },
    )
    db.add(row)
    db.commit()


def _analysis(db, *, record_id: int, user_id: int, is_deleted: int = 0) -> AnalysisRecord:
    row = AnalysisRecord(
        id=record_id,
        user_id=user_id,
        resume_id=1,
        jd_id=1,
        match_score=60,
        match_report={},
        optimize_suggestions={},
        interview_questions={},
        is_deleted=is_deleted,
    )
    db.add(row)
    db.commit()
    return row


def _task_with_step(db, record_id: int, output: dict, *, step_name: str = "career_planning") -> AgentTask:
    task = AgentTask(
        user_id=1,
        resume_id=1,
        jd_id=1,
        analysis_record_id=record_id,
        status="completed",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    db.add(
        AgentStepLog(
            task_id=task.id,
            step_name=step_name,
            step_index=1,
            status="completed",
            output_data=output,
        )
    )
    db.commit()
    return task


def _plan(*gaps) -> dict:
    return {"skill_gaps": list(gaps)}


def test_legacy_alias_gap_is_the_only_thing_backfill_would_gain(db_session):
    _interview(db_session, 1)
    _analysis(db_session, record_id=1, user_id=1)
    # K8s 与画像的 Kubernetes 只差别名；Kafka 画像里没有；MySQL 不是弱点。
    _task_with_step(db_session, 1, _plan({"skill": "K8s"}, {"skill": "Kafka"}, {"skill": "MySQL"}))

    report = radius.build_report(db_session, 15)
    s = report["summary"]
    assert s["gaps_total"] == 3
    assert s["gaps_legacy"] == 3
    assert s["gaps_with_canonical"] == 0
    assert s["legacy_alias_hits"] == 1
    assert s["legacy_would_gain"] == 1
    assert s["legacy_no_match"] == 2
    assert s["records_that_would_gain"] == 1
    assert report["detail"][0]["would_gain"] == ["K8s"]
    assert report["detail"][0]["would_gain_canonicals"] == ["kubernetes"]


def test_gaps_that_already_carry_canonical_are_not_backfill_radius(db_session):
    _interview(db_session, 1)
    _analysis(db_session, record_id=2, user_id=1)
    _task_with_step(
        db_session,
        2,
        _plan({"skill": "K8s", "canonical": "kubernetes"}, {"skill": "Redis", "canonical": "redis"}),
    )

    report = radius.build_report(db_session, 15)
    s = report["summary"]
    assert s["gaps_legacy"] == 0
    assert s["gaps_with_canonical"] == 2
    assert s["canonical_matched"] == 1
    assert s["canonical_no_match"] == 1
    assert s["legacy_would_gain"] == 0
    assert s["records_that_would_gain"] == 0


def test_spelling_match_is_not_counted_as_backfill_gain(db_session):
    _interview(db_session, 1)
    _analysis(db_session, record_id=3, user_id=1)
    _task_with_step(db_session, 3, _plan({"skill": "Kubernetes"}))

    s = radius.build_report(db_session, 15)["summary"]
    assert s["legacy_matched_by_spelling"] == 1
    assert s["legacy_would_gain"] == 0, "现在就已经对上画像的缺口，不是回填的收益"
    assert s["records_that_would_gain"] == 0


def test_nested_summary_plan_is_read_and_empty_gaps_are_not_legacy(db_session):
    _interview(db_session, 1)
    _analysis(db_session, record_id=4, user_id=1)
    _task_with_step(db_session, 4, {"career_planning": _plan({"skill": "K8s"})}, step_name="summary")
    _analysis(db_session, record_id=5, user_id=1)
    _task_with_step(db_session, 5, _plan({"skill": ""}, "Redis"))  # 空技能名 + 字符串形状

    s = radius.build_report(db_session, 15)["summary"]
    assert s["records_without_gaps"] == 0
    assert s["gaps_total"] == 3
    assert s["empty_gaps"] == 1
    assert s["gaps_legacy"] == 2
    assert s["legacy_would_gain"] == 1, "嵌套那份里的 K8s 也要能算进回填收益"


def test_records_without_task_plan_or_gaps_are_counted_not_dropped(db_session):
    _analysis(db_session, record_id=6, user_id=1)
    _analysis(db_session, record_id=7, user_id=1)
    _task_with_step(db_session, 7, {"visual_roadmap": {}}, step_name="summary")
    _analysis(db_session, record_id=8, user_id=1, is_deleted=1)
    _task_with_step(db_session, 8, _plan({"skill": "K8s"}))
    _analysis(db_session, record_id=9, user_id=1)
    _task_with_step(db_session, 9, _plan())

    s = radius.build_report(db_session, 15)["summary"]
    assert s["records_total"] == 4
    assert s["records_deleted"] == 1
    assert s["records_without_task"] == 1
    assert s["records_without_plan"] == 1
    assert s["records_without_gaps"] == 1
    assert s["records_with_legacy_gaps"] == 1
    # 软删的记录仍然进半径：回填是数据层的决定，不该由界面可见性替它筛。
    assert s["gaps_total"] == 1


def test_the_radius_script_never_writes(db_session, capsys, monkeypatch):
    _interview(db_session, 1)
    _analysis(db_session, record_id=9, user_id=1)
    _task_with_step(db_session, 9, _plan({"skill": "K8s"}))

    def _no_write(self, *args, **kwargs):
        raise AssertionError("半径脚本写了库——回填是另一次拍板，这里不许动手")

    monkeypatch.setattr(radius, "SessionLocal", lambda: db_session)
    db_session.autoflush = False
    monkeypatch.setattr(Session, "commit", _no_write)
    monkeypatch.setattr(Session, "flush", _no_write)

    assert radius.main(["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["legacy_would_gain"] == 1
    assert payload["detail"][0]["record_id"] == 9

    with pytest.raises(AssertionError, match="写了库"):
        db_session.commit()
    with pytest.raises(AssertionError, match="写了库"):
        db_session.flush()
