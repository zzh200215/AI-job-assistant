"""P4 跨会话画像：把已完成会话的报告压成维度/技能弱点。

这一层是三条回流的共同数据源（简历改写、学习建议、下一场考察重点），所以判据分三层：

1. **纯函数**：哪些分数算弱点；超时不算技能证据；"没考到"与"考了不会"分开；
2. **合并**：同一 session 重放不许双计；多场按样本加权去重；窗口只留最近 10 场；
3. **路由**：只返回当前用户的画像，空画像有稳定形状。

画像按需从已完成会话派生，不落库——原稿给的是"新表或 user JSON 列"，这里改用派生：
未执行的迁移会让 `tb_user` 的每条查询当场 Unknown column（P1.2 的教训），而画像是已完成
报告的纯函数，数据量只有几十场，先不引入这笔持久化。将来有性能证据再谈列。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.api.interview_rest import interview_profile
from app.models.interview_session import InterviewSession
from app.services.interview_profile_service import (
    MAX_SESSIONS,
    WEAK_DIMENSION_THRESHOLD,
    WEAK_SKILL_THRESHOLD,
    build_profile,
    build_session_summary,
    compact_profile,
    get_profile,
    merge_profile,
    public_profile,
)


def _report(
    *,
    overall: int = 64,
    dimensions: dict | None = None,
    questions: list[dict] | None = None,
    required: list[str] | None = None,
    weaknesses: list[str] | None = None,
) -> dict:
    return {
        "overall_score": overall,
        "dimension_scores": dimensions
        if dimensions is not None
        else {"completeness": 80, "accuracy": 75, "depth": 58, "expression": 60},
        "question_evaluations": questions
        if questions is not None
        else [
            {
                "question": "Kafka 的消费语义怎么保证不丢消息？",
                "overall_score": 55,
                "feedback": "只说了 at-least-once",
                "improvement": "补幂等与去重",
            },
            {
                "question": "Redis 缓存穿透怎么处理？",
                "overall_score": 85,
                "feedback": "思路完整",
                "improvement": "",
            },
            {
                "question": "讲一次线上故障排查。",
                "overall_score": 62,
                "feedback": "缺少指标",
                "improvement": "补数据",
            },
        ],
        "answered_questions": len(questions) if questions is not None else 3,
        "strengths": ["表达清楚"],
        "weaknesses": weaknesses if weaknesses is not None else ["成果未量化", "结构混乱"],
        "interview_memory": {"jd_required_skills": required or ["Kafka", "Redis", "容量规划"]},
    }


def _session(
    *,
    session_id: int = 1,
    user_id: int = 1,
    completed_at: datetime | None = None,
    evaluation_status: str = "completed",
    status: str = "completed",
    **report_overrides,
) -> InterviewSession:
    return InterviewSession(
        id=session_id,
        user_id=user_id,
        tenant_id=1,
        interview_type="tech",
        status=status,
        evaluation=_report(**report_overrides),
        evaluation_status=evaluation_status,
        completed_at=completed_at or datetime(2026, 10, 1),
    )


def test_dimension_and_skill_weaknesses_are_structured():
    summary = build_session_summary(_session())

    assert summary is not None
    assert summary["dimensions"]["depth"] == 58
    assert summary["dimensions"]["completeness"] == 80
    weak_dims = {row["dimension"]: row["avg_score"] for row in summary["dimension_weaknesses"]}
    assert weak_dims == {"depth": 58, "expression": 60}
    assert WEAK_DIMENSION_THRESHOLD == 65

    weak_skills = {row["canonical"]: row for row in summary["skill_weaknesses"]}
    assert weak_skills["kafka"]["avg_score"] == 55
    assert weak_skills["kafka"]["samples"] == 1
    assert "redis" not in weak_skills
    assert WEAK_SKILL_THRESHOLD == 70
    assert summary["unasked_required"] == ["容量规划"]
    assert summary["weakness_texts"] == ["成果未量化", "结构混乱"]
    assert summary["overall_score"] == 64


def test_a_timeout_is_not_skill_evidence_and_not_unasked():
    """超时题不能拿来证明"这项技能不会"（P3 同一条纪律），也不能算"没考到"。"""
    summary = build_session_summary(
        _session(
            questions=[
                {
                    "question": "Kafka 的消费语义怎么保证不丢消息？",
                    "overall_score": 0,
                    "timed_out": True,
                    "feedback": "超时",
                    "improvement": "",
                },
                {
                    "question": "讲一次线上故障排查。",
                    "overall_score": 70,
                    "feedback": "有过程",
                    "improvement": "补指标",
                },
            ],
            required=["Kafka", "Redis"],
        )
    )

    assert summary is not None
    assert summary["skill_weaknesses"] == []
    assert summary["unanswered_required"] == ["Kafka"]
    assert summary["unasked_required"] == ["Redis"]


def test_skill_aliases_match_the_canonical_vocabulary():
    summary = build_session_summary(
        _session(
            questions=[
                {
                    "question": "Kubernetes 集群怎么做滚动发布？",
                    "overall_score": 48,
                    "feedback": "没有提探针",
                    "improvement": "补 readiness/liveness",
                }
            ],
            required=["K8s"],
        )
    )

    assert summary is not None
    assert summary["skill_weaknesses"][0]["canonical"] == "kubernetes"
    assert summary["skill_weaknesses"][0]["avg_score"] == 48


def test_short_skill_names_do_not_match_inside_other_words():
    """`Go` 不许在 `Google` 里命中——短 ASCII 技能名必须按词边界匹配。"""
    summary = build_session_summary(
        _session(
            questions=[
                {
                    "question": "Google 的 BigQuery 怎么控制成本？",
                    "overall_score": 40,
                    "feedback": "只说了分区",
                    "improvement": "补预算",
                }
            ],
            required=["Go"],
        )
    )

    assert summary is not None
    assert summary["skill_weaknesses"] == []
    assert summary["unasked_required"] == ["Go"]


def test_merge_is_idempotent_by_session_id():
    summary = build_session_summary(_session(session_id=7))
    once = merge_profile({}, summary)
    twice = merge_profile(once, summary)

    assert once["session_count"] == 1
    assert twice["session_count"] == 1
    assert twice["total_sessions"] == 1
    assert twice["skill_weaknesses"] == once["skill_weaknesses"]
    assert twice["dimension_weaknesses"] == once["dimension_weaknesses"]


def test_merge_weights_skill_scores_by_samples():
    low = build_session_summary(
        _session(
            session_id=1,
            questions=[
                {
                    "question": "Kafka 消费语义？",
                    "overall_score": 50,
                    "feedback": "浅",
                    "improvement": "补",
                }
            ],
            required=["Kafka"],
        )
    )
    high = build_session_summary(
        _session(
            session_id=2,
            questions=[
                {"question": "Kafka 顺序写怎么保证？", "overall_score": 80},
                {"question": "Kafka 分区怎么选？", "overall_score": 80},
                {"question": "Kafka 重平衡怎么避免？", "overall_score": 80},
            ],
            required=["Kafka"],
        )
    )

    merged = merge_profile(merge_profile({}, low), high)

    assert merged["session_count"] == 2
    kafka = next(row for row in merged["skill_weaknesses"] + merged["skill_scores"] if row["canonical"] == "kafka")
    assert kafka["samples"] == 4
    assert kafka["sessions"] == 2
    assert kafka["avg_score"] == 72.5
    assert all(row["canonical"] != "kafka" for row in merged["skill_weaknesses"])


def test_merge_keeps_only_the_recent_window():
    profile = {}
    for session_id in range(1, MAX_SESSIONS + 3):
        summary = build_session_summary(_session(session_id=session_id))
        assert summary is not None
        profile = merge_profile(profile, summary)

    assert profile["session_count"] == MAX_SESSIONS
    assert profile["session_ids"] == list(range(3, MAX_SESSIONS + 3))
    assert MAX_SESSIONS == 10


def test_get_profile_derives_only_from_completed_sessions(db_session, normal_user, make_interview_session):
    completed_id = make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )
    make_interview_session(
        user_id=normal_user.id,
        status="ongoing",
        evaluation=_report(weaknesses=["不该出现"]),
        evaluation_status="idle",
        completed_at=None,
    )

    profile = get_profile(db_session, normal_user.id)
    public = public_profile(profile)

    assert public["has_data"] is True
    assert public["total_sessions"] == 1
    assert public["last_session"]["session_id"] == completed_id
    assert public["skill_weaknesses"][0]["canonical"] == "kafka"


def test_get_profile_accepts_legacy_idle_status_with_question_evaluations(
    db_session, normal_user, make_interview_session
):
    """旧结束路径把 evaluation_status 留在 idle，但报告里的逐题评分是齐的。"""
    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="idle",
        completed_at=datetime(2026, 10, 2),
    )

    public = public_profile(get_profile(db_session, normal_user.id))

    assert public["has_data"] is True
    assert public["total_sessions"] == 1
    assert public["skill_weaknesses"][0]["canonical"] == "kafka"


def test_get_profile_skips_processing_even_with_question_evaluations(db_session, normal_user, make_interview_session):
    """processing 是“还在评”，哪怕报告里已有部分逐题评分也不能算进画像。"""
    report = _report()
    report["evaluation_status"] = "processing"
    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=report,
        evaluation_status="processing",
        completed_at=datetime(2026, 10, 2),
    )

    public = public_profile(get_profile(db_session, normal_user.id))

    assert public["has_data"] is False
    assert public["total_sessions"] == 0


def test_empty_profile_has_a_stable_shape(db_session, normal_user):
    public = public_profile(build_profile(db_session, normal_user.id))

    assert public["has_data"] is False
    assert public["total_sessions"] == 0
    assert public["session_count"] == 0
    assert public["skill_weaknesses"] == []
    assert public["dimension_weaknesses"] == []
    assert public["last_session"] is None


def test_profile_route_is_mounted():
    """函数级测试证明不了路径：这一条钉住 `/api/interview/profile` 真的挂进了总路由。"""
    from app.api.router import api_router

    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert "/interview/profile" in paths


def test_route_returns_the_current_users_profile(db_session, normal_user, make_interview_session):
    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )

    body = interview_profile(db=db_session, current_user=normal_user)

    assert body["code"] == 0
    assert body["data"]["has_data"] is True
    assert body["data"]["skill_weaknesses"][0]["canonical"] == "kafka"
    assert "sessions" not in body["data"]


def test_compact_profile_keeps_only_the_focus_fields():
    compact = compact_profile(
        {
            "skill_weaknesses": [
                {
                    "skill": "Kafka",
                    "canonical": "kafka",
                    "avg_score": 55,
                    "sessions": 2,
                    "samples": 3,
                    "evidence": [{"question": "不该进快照"}],
                }
            ],
            "dimension_weaknesses": [{"dimension": "depth", "label": "深度", "avg_score": 58, "sessions": 2}],
            "weakness_texts": ["成果未量化", "结构混乱"],
            "last_session": {"session_id": 7},
            "sessions": [{"session_id": 7}],
        }
    )

    assert compact["skill_weaknesses"] == [{"skill": "Kafka", "canonical": "kafka", "avg_score": 55, "sessions": 2}]
    assert compact["dimension_weaknesses"] == [{"dimension": "depth", "label": "深度", "avg_score": 58}]
    assert compact["weakness_texts"] == ["成果未量化", "结构混乱"]
    assert compact["last_session"] == {"session_id": 7}
    assert "sessions" not in compact


def test_create_session_snapshot_carries_prior_profile(db_session, normal_user, make_interview_session):
    """回流③的接线：建会话那一刻把上一场画像写进快照，而不是等决策器自己查库。"""
    from fastapi import BackgroundTasks

    from app.api.interview_rest import create_session
    from app.models.history import JobDescription, Resume
    from app.schemas.interview_session import InterviewSessionCreate

    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )
    resume = Resume(
        user_id=normal_user.id,
        tenant_id=1,
        name="画像验证简历",
        file_name="profile.pdf",
        file_path="uploads/profile.pdf",
        file_type="pdf",
        file_size=1,
        parsed_json={"skills": ["Python"]},
        is_deleted=0,
    )
    jd = JobDescription(
        user_id=normal_user.id,
        tenant_id=1,
        title="后端工程师",
        company="示例公司",
        raw_text="后端工程师",
        is_active=1,
        parsed_json={"title": "后端工程师", "required_skills": ["Kafka", "Redis"]},
    )
    db_session.add_all([resume, jd])
    db_session.commit()
    db_session.refresh(resume)
    db_session.refresh(jd)

    body = create_session(
        InterviewSessionCreate(resume_id=resume.id, jd_id=jd.id, interview_type="tech"),
        BackgroundTasks(),
        db=db_session,
        current_user=normal_user,
    )

    assert body["code"] == 0
    created = (
        db_session.query(InterviewSession)
        .filter(InterviewSession.user_id == normal_user.id)
        .order_by(InterviewSession.id.desc())
        .first()
    )
    assert created is not None
    profile = created.memory_snapshot["interview_profile"]
    assert profile["skill_weaknesses"][0]["canonical"] == "kafka"
    assert profile["last_session"]["session_id"] is not None
    assert "sessions" not in profile


def test_create_session_tilts_the_opening_questions_toward_prior_weakness(
    db_session, normal_user, make_interview_session
):
    """回流③的可见效果：上一场弱项 Kafka 在本场必考项里，就把它那道题排到开场第一。"""
    from fastapi import BackgroundTasks

    from app.api.interview_rest import create_session
    from app.models.history import JobDescription, Resume
    from app.schemas.interview_session import InterviewSessionCreate

    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )
    resume = Resume(
        user_id=normal_user.id,
        tenant_id=1,
        name="倾斜验证简历",
        file_name="tilt.pdf",
        file_path="uploads/tilt.pdf",
        file_type="pdf",
        file_size=1,
        parsed_json={"skills": ["Python"]},
        is_deleted=0,
    )
    jd = JobDescription(
        user_id=normal_user.id,
        tenant_id=1,
        title="后端工程师",
        company="示例公司",
        raw_text="后端工程师",
        is_active=1,
        parsed_json={"title": "后端工程师", "required_skills": ["Redis", "Kafka"]},
    )
    db_session.add_all([resume, jd])
    db_session.commit()
    db_session.refresh(resume)
    db_session.refresh(jd)

    body = create_session(
        InterviewSessionCreate(resume_id=resume.id, jd_id=jd.id, interview_type="tech"),
        BackgroundTasks(),
        db=db_session,
        current_user=normal_user,
    )

    assert body["code"] == 0
    created = (
        db_session.query(InterviewSession)
        .filter(InterviewSession.user_id == normal_user.id)
        .order_by(InterviewSession.id.desc())
        .first()
    )
    texts = [row["question"] for row in created.questions]
    intro = next(index for index, text in enumerate(texts) if "请用 2 分钟" in text)
    assert intro > 0, texts[:3]
    assert "Kafka" in texts[0], texts[:3]
    # 命中弱项的题全部排在开场介绍之前，且各自保持原顺序。
    assert all("Kafka" in text or "Redis" in text for text in texts[:intro]), texts[:3]


def test_build_profile_orders_sessions_by_completion(db_session, normal_user, make_interview_session):
    base = datetime(2026, 10, 1)
    first = make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=base + timedelta(days=1),
    )
    second = make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=base + timedelta(days=2),
    )

    profile = get_profile(db_session, normal_user.id)

    assert profile["last_session"]["session_id"] == second
    assert profile["session_ids"] == [first, second]


# ---------------------------------------------------------------- 本场重点（jd_focus）


def _job(db, user, *, title="后端开发工程师", required=("Kafka", "Python"), tenant_id=1):
    from app.models.history import JobDescription

    row = JobDescription(
        user_id=user.id,
        tenant_id=tenant_id,
        title=title,
        company="示例",
        raw_text="",
        parsed_json={"title": title, "required_skills": list(required)},
        source="manual",
        is_active=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_jd_focus_lists_only_the_weaknesses_the_job_requires(db_session, normal_user, make_interview_session):
    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )
    jd = _job(db_session, normal_user, required=["Kafka", "Python"])

    body = interview_profile(jd_id=jd.id, db=db_session, current_user=normal_user)

    focus = body["data"]["jd_focus"]
    assert focus["jd_id"] == jd.id
    assert focus["required_count"] == 2
    assert [row["canonical"] for row in focus["overlap"]] == ["kafka"]
    assert focus["overlap"][0]["avg_score"] == 55


def test_jd_focus_uses_the_shared_alias_table(db_session, normal_user, make_interview_session):
    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(
            required=["Kubernetes"],
            questions=[
                {"question": "Kubernetes 的调度怎么做？", "overall_score": 50, "feedback": "只说了概念"},
            ],
        ),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )
    jd = _job(db_session, normal_user, required=["K8s", "Go"])

    focus = interview_profile(jd_id=jd.id, db=db_session, current_user=normal_user)["data"]["jd_focus"]

    assert [row["canonical"] for row in focus["overlap"]] == ["kubernetes"]
    assert focus["overlap"][0]["skill"] == "Kubernetes"


def test_profile_without_jd_keeps_the_old_shape(db_session, normal_user):
    body = interview_profile(db=db_session, current_user=normal_user)

    assert body["code"] == 0
    assert "jd_focus" not in body["data"]


def test_jd_focus_is_empty_for_a_job_the_user_cannot_see(db_session, normal_user):
    foreign = _job(db_session, normal_user, required=["Kafka"], tenant_id=1)
    foreign.user_id = normal_user.id + 1000
    db_session.commit()

    focus = interview_profile(jd_id=foreign.id, db=db_session, current_user=normal_user)["data"]["jd_focus"]

    assert focus == {"jd_id": foreign.id, "title": "", "required_count": 0, "overlap": []}
