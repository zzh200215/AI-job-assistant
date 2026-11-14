"""A4: one (resume, job) pair must have exactly one displayed match score.

Before this, three paths computed three numbers — the recommend engine's
vector/rule blend, the explainer's 6-dimension rubric, and a raw LLM score — and
none of them applied the weak-fit cap, so the recommend page and the explain page
could disagree about the same job.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.security import hash_password
from app.models.history import JobDescription, Resume
from app.models.match_score import MatchScore
from app.models.user import User
from app.services.match_explainer_service import MatchExplainer
from app.services.match_score_service import (
    canonical_match_score,
    compute_canonical_score,
    resume_version_of,
)
from app.services.scoring_config import SCORE_METHOD


def _user(db, name="a4_user"):
    user = User(
        username=name,
        email=f"{name}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resume(db, user, skills, years=3, self_eval="三年经验"):
    row = Resume(
        user_id=user.id,
        name="a4 resume",
        file_name="a4.pdf",
        file_path="uploads/a4.pdf",
        file_type="pdf",
        file_size=1024,
        parsed_json={
            "name": "张三",
            "skills": skills,
            "years_exp": years,
            "education": "本科",
            "project_experience": [],
            "self_evaluation": self_eval,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db, user, required, title="后端工程师", experience_requirement=""):
    row = JobDescription(
        user_id=user.id,
        title=title,
        company="示例公司",
        location="上海",
        raw_text=f"{title} 示例公司",
        is_active=1,
        parsed_json={
            "title": title,
            "required_skills": required,
            "nice_to_have": [],
            "experience_requirement": experience_requirement,
            "education_requirement": "本科",
            "keywords": [],
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_rubric_does_not_mutate_the_objects_it_scores(db_session):
    """A scoring function must not write into the resume it is reading.

    compute_rubric backfills compatibility fields; they used to land on the live
    parsed_json dict, so `skills: []` could be persisted onto a real resume and
    scoring the same pair twice produced different numbers.
    """
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python"])

    before_resume = dict(resume.parsed_json)
    before_jd = dict(jd.parsed_json)

    MatchExplainer().compute_rubric(resume, jd)

    assert resume.parsed_json == before_resume, "compute_rubric mutated resume.parsed_json"
    assert jd.parsed_json == before_jd, "compute_rubric mutated jd.parsed_json"


def test_scoring_the_same_pair_twice_is_stable(db_session):
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI", "Docker"])
    jd = _job(db_session, user, ["Python", "Kubernetes"])

    first = compute_canonical_score(resume, jd)["score"]
    second = compute_canonical_score(resume, jd)["score"]

    assert first == second


def test_explain_and_canonical_agree_on_the_same_number(db_session):
    """The acceptance criterion: recommend and explain cannot disagree."""
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python", "PostgreSQL"])

    canonical = canonical_match_score(db_session, resume, jd, user_id=user.id)["score"]
    explained = MatchExplainer().explain(resume, jd).overall_score

    assert round(float(explained), 1) == round(float(canonical), 1)


def test_weak_fit_cap_applies_on_the_canonical_path(db_session):
    """The cap used to run only inside the agent graph, never on the two paths
    candidates actually see.

    Note the limit of the current implementation: infer_match_score_cap only
    recognises three role shapes (全栈 / 高级产品经理 / 技术项目经理), so this is a
    targeted guard, not a general weak-fit detector.
    """
    user = _user(db_session)
    # Frontend-only candidate against a full-stack role: has_frontend true,
    # has_backend and has_db both absent, which is the documented cap-55 case.
    resume = _resume(
        db_session,
        user,
        ["React", "TypeScript"],
        years=3,
        self_eval="三年界面开发经验",
    )
    jd = _job(
        db_session,
        user,
        ["React", "Node.js", "PostgreSQL"],
        title="全栈工程师",
    )

    result = compute_canonical_score(resume, jd)

    assert result["cap_applied"] == 55
    # The invariant is that the displayed score never exceeds the cap; whether it
    # binds depends on the rubric score itself.
    assert result["score"] == round(min(result["raw_score"], 55.0), 1)


def test_canonical_score_is_persisted_once_per_pair(db_session):
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python"])
    jd = _job(db_session, user, ["Python"])

    canonical_match_score(db_session, resume, jd, user_id=user.id)
    canonical_match_score(db_session, resume, jd, user_id=user.id)

    rows = db_session.query(MatchScore).filter(MatchScore.resume_id == resume.id, MatchScore.jd_id == jd.id).all()
    assert len(rows) == 1
    assert rows[0].method == SCORE_METHOD
    assert rows[0].resume_version == resume_version_of(resume)


def test_recommend_engine_reports_the_canonical_score(monkeypatch, db_session):
    """The engine may still rank by its blend internally, but the number it hands
    the UI must be the canonical one."""
    from app.services import job_recommend_engine as engine_mod

    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python"])

    engine = engine_mod.JobRecommendationEngine(db_session)
    results = engine.recommend(resume.id, limit=5, bypass_cache=True)

    assert results, "expected at least one recommendation"
    by_id = {item["jd_id"]: item for item in results}
    assert jd.id in by_id

    canonical = canonical_match_score(db_session, resume, jd, user_id=user.id, persist=False)["score"]
    assert round(float(by_id[jd.id]["match_score"])) == round(float(canonical))
    assert by_id[jd.id]["match_score_method"] == SCORE_METHOD
    # Retrieval signal is still reported, but as a separate diagnostic field.
    assert "retrieval_score" in by_id[jd.id]


def test_resume_without_stated_tenure_does_not_crash_the_rubric(db_session):
    """`resume.get("years_exp", 0)` yields None when the key exists but is null,
    which made `abs(None - jd_mid)` raise and 500 /explain-match for any resume
    parsed without a stated tenure."""
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python"])
    resume.parsed_json = {**resume.parsed_json, "years_exp": None}
    jd = _job(db_session, user, ["Python"], experience_requirement="3-5年")

    result = compute_canonical_score(resume, jd)

    assert 0 <= result["score"] <= 100
    exp = next(d for d in result["dimensions"] if d["name"] == "工作经验")
    assert any("未标注工作年限" in detail for detail in exp["details"])


def test_coerce_years_distinguishes_absent_from_zero():
    coerce = MatchExplainer._coerce_years

    assert coerce(None) is None
    assert coerce("") is None
    assert coerce("未提及") is None
    assert coerce(0) == 0.0
    assert coerce("3年") == 3.0
    assert coerce(3.5) == 3.5


def test_orchestration_records_the_canonical_score_not_the_models_own_number(db_session):
    """C7 查出来的漏网：默认编排路径把模型自报的 match_score 直接写进分析记录。

    A4 说匹配分只有一个来源，但 `AnalysisRecord.match_score` 存的是模型在 JSON 里
    随口报的数（85 就是 85），推荐页/解释页用的是另一套规则分——同一对简历+岗位
    于是有两个"匹配分"。
    """
    from app.models.history import AnalysisRecord
    from app.orchestration.context import AgentContext
    from app.orchestration.strategies import LinearStrategy

    user = _user(db_session, name="c7_score_user")
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python", "FastAPI", "Kubernetes"])

    context = AgentContext.for_analysis(resume.id, jd.id, user_id=user.id, db=db_session)
    context.match_result = {"match_score": 99, "summary": "模型自评"}

    record_id = LinearStrategy.__new__(LinearStrategy)._save_analysis_record(
        db_session, resume.id, jd.id, user.id, context
    )

    record = db_session.get(AnalysisRecord, record_id)
    canonical = compute_canonical_score(resume, jd)
    assert record.match_score == int(round(canonical["score"]))
    assert record.match_score != 99
    # 模型自报数仍在，作为对照证据而不是显示分
    assert record.match_report["model_reported_score"] == 99
    assert record.match_report["score_method"] == SCORE_METHOD


def test_orchestration_marks_the_score_unavailable_instead_of_borrowing_the_llm_number(db_session):
    """简历/JD 不可见时宁可标"未算出"，也不回退成模型自报数。"""
    from app.models.history import AnalysisRecord, JobDescription, Resume
    from app.orchestration.context import AgentContext
    from app.orchestration.strategies import LinearStrategy

    context = AgentContext.for_analysis(9998, 9999, user_id=1, db=db_session)
    context.match_result = {"match_score": 88}

    record_id = LinearStrategy.__new__(LinearStrategy)._save_analysis_record(db_session, 9998, 9999, 1, context)

    record = db_session.get(AnalysisRecord, record_id)
    assert record.match_score == 0
    assert record.match_report["model_reported_score"] == 88
    assert "无法按权威算法重算" in record.match_report["score_unavailable_reason"]
    assert db_session.get(Resume, 9998) is None and db_session.get(JobDescription, 9999) is None


MARKER_WRITE = re.compile(r'([A-Za-z_]\w*)\["(\w*(?:method|cap|gap|raw)\w*)"\]\s*=')
RECORD_WRITE = re.compile(r"=\s*AnalysisRecord\(")

# 该写的权威量，基准是 `strategies.py:262-264`。
CANONICAL_REPORT_KEYS = {"score_method", "cap_applied", "skill_gap"}
# 词表：这一族里允许出现在新写入中的键名。`match_score_raw` 曾经只有 match_service 写，
# 那个写入方 2026-11-14 随 `POST /analysis/match` 一起出树，所以词表收回到这三个。
ALLOWED_REPORT_KEYS = set(CANONICAL_REPORT_KEYS)


def _app_sources():
    root = Path(__file__).resolve().parents[1] / "app"
    return {p: p.read_text(encoding="utf-8") for p in root.rglob("*.py")}


def report_keys_written_into_a_match_report(sources: dict) -> dict[str, list[str]]:
    """扫"往名字里带 match 的字典里盖 method/cap/gap/raw 类键"的赋值。

    必须按目标变量名筛一遍：`runtime_metrics.py` 里有一处 `["method_totals"] = `，那是请求计数器的
    桶名，与匹配分无关——**这条我自己先撞了一次**（不加筛就是假阳性）。
    """
    found: dict[str, list[str]] = {}
    for path, text in sources.items():
        for target, key in MARKER_WRITE.findall(text):
            if "match" in target.lower():
                found.setdefault(key, []).append(path.name)
    return found


def test_analysis_record_has_exactly_one_writer():
    """`AnalysisRecord` 只能有一个写入方：编排链路的 `_save_analysis_record`。

    2026-11-14 之前有两个：`match_service.run_full_analysis`（`POST /analysis/match` 那条一次性三步）
    也直接 `AnalysisRecord(...)`。两条路径的 `match_report` 键名曾经分叉，而分叉的后果只有回算脚本
    看得见（值相同、Δ0、半径虚高）——所以"只有一个写入方"不只是整洁，它是上面那条词表判据能成立的
    前提：一旦出现第二个写入方，你就得重新证明两份词表一致，而不能靠"本来就只有一条"。
    """
    sources = _app_sources()
    writers = sorted(path.name for path, text in sources.items() if RECORD_WRITE.search(text))

    assert writers == ["strategies.py"], f"分析记录的写入方不止一个：{writers}"


def test_the_one_write_path_that_is_left_stamps_the_canonical_vocabulary():
    """A4 + D166/D169 的收敛版：`AnalysisRecord.match_report` 现在只有一个写入方。

    原来这条钉的是"两条落库路径必须用同一组键名"——`strategies.py` 与 `match_service.py`
    曾经分叉（后者写 `match_score_method` / `match_score_cap_applied` 且不写 `skill_gap`），
    而全树唯一的读者是回算脚本，所以后果不是报错而是**半径虚高**。

    2026-11-14，那个一次性三步的 `POST /analysis/match`（连同 `match_service`）出树
    （见 `docs/真provider实测.md` §7）：分叉的两条路只剩一条，"对齐"这件事由**没有第二条可对齐**
    代替。门不能因此退化成"没人写就不算分叉"——词表外的键名照样红，而且现在要求每个权威量
    恰好只有那一个写入方。

    射程：`xxx["key"] = ` 这种赋值形式，且目标变量名里得带 `match`（不然被 `method_totals` 顶出
    假阳性）。`job_recommend_engine.py:222` 的 `"match_score_method": …` 是**推荐接口自己的响应字段**
    （dict 字面量，不是这种赋值），不在这一条里——别把它读成"还有第二种拼法"。
    """
    sources = _app_sources()
    written = report_keys_written_into_a_match_report(sources)

    assert set(written) <= ALLOWED_REPORT_KEYS, f"这一族里出现了词表外的键名：{written}"
    for key in CANONICAL_REPORT_KEYS:
        assert written.get(key) == ["strategies.py"], f"{key} 的写入方不唯一：{written.get(key)}"

    # 反证（打在副本上，不动工作树）：D166 那个旧标记键、D169 那个旧 cap 键，塞回去都必须被认出来。
    strategies = next(p for p in sources if p.name == "strategies.py")
    for old, new in (
        ('match_result["score_method"]', 'match_result["match_score_method"]'),
        ('match_result["cap_applied"]', 'match_result["match_score_cap_applied"]'),
    ):
        assert old in sources[strategies], f"锚点变了（{old}），反证落不进副本"
        discovered = report_keys_written_into_a_match_report({strategies: sources[strategies].replace(old, new)})
        bad = new.split('"')[1]
        assert bad in discovered, f"{bad} 这种拼法必须被这条门认出来"
        assert not set(discovered) <= ALLOWED_REPORT_KEYS, f"{bad} 竟然还算在词表里——等于没装门"
