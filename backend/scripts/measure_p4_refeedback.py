#!/usr/bin/env python
"""P4 回流测量的仪器（`简历与面试优化.md` §4 P4）。

测两件事，各两臂，**只差一个变量**：

* `rewrite`：同一份简历/JD，带上一场面试弱点提示 vs 不带（`user_id=None` 走通用提示）。
* `career`：同一批岗位方向，带面试证据 vs 不带（`attach_interview_evidence` 贴/不贴）。
  量的是 `/career-path/recommend` 的活路径 `CareerPathAgent`；orchestration 的 `CareerAgent`
  prompt 里没有 `interview_profile`，结构上拿不到这份证据，不在本测量里。

mock 下验的是**仪器**（提示确实进了 prompt、证据确实贴到缺口、夹具两臂同源）；
真实建议/理由的质量要 `--allow-real` 那一发，由 `reports/p4_refeedback_review.md` 的人工评分表判。
这不是又一条发布门，所以它没有 `check_thresholds`，也不进 CI。

跑法：
    python scripts/measure_p4_refeedback.py                 # mock，零花费，验仪器
    python scripts/measure_p4_refeedback.py --allow-real    # 4 发真 provider（花钱，需点名）

每次都写 `reports/p4_refeedback_latest.json` 与复核表；数据库固定是**进程内 sqlite**，
不连 `llmXM`，也不碰 `uploads/`。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# 必须在任何 app import 之前钉死：这条测量绝不能连到开发机 .env 里的 MySQL。
os.environ.setdefault("TESTING", "true")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("RUN_SCHEDULER", "false")
os.environ.setdefault("ORCHESTRATION_BACKEND", "thread")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import BigInteger, func  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


# SQLite 只把 `INTEGER PRIMARY KEY` 当 rowid 别名；模型清一色 BigInteger PK。
# 这条钩子必须挂在任何 DDL 之前，否则夹具插不进去（与 tests/conftest.py 同因）。
@compiles(BigInteger, "sqlite")
def _compile_big_integer_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


import app.models  # noqa: E402, F401
from app.agents import career_path_agent  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.history import JobDescription, Resume  # noqa: E402
from app.models.interview_session import InterviewSession  # noqa: E402
from app.models.prompt_trace import PromptTrace  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import resume_rewrite_service  # noqa: E402
from app.services.career_evidence import attach_interview_evidence, derive_directions  # noqa: E402
from app.services.interview_profile_service import get_profile, public_profile  # noqa: E402
from app.services.llm_service import get_llm_provenance  # noqa: E402
from scripts.provider_guard import require_mock  # noqa: E402

FIXTURE = ROOT / "tests/eval/p4_refeedback_cases.json"
DEFAULT_OUTPUT = ROOT / "reports/p4_refeedback_latest.json"
DEFAULT_REVIEW = ROOT / "reports/p4_refeedback_review.md"

MOCK_REWRITE = {
    "suggestions": [
        {
            "block_id": "self_evaluation",
            "original": "三年后端开发经验",
            "proposed_text": "三年后端开发经验，主导订单链路优化",
            "reason": "把已有经历写得更具体",
        }
    ]
}

REWRITE_SOURCE = "resume_rewrite_service.build_rewrite_suggestions"
CAREER_SOURCE = "career_path_agent.recommend"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed(db, case: dict[str, Any]) -> tuple[User, Resume, JobDescription]:
    suffix = uuid4().hex[:8]
    user = User(
        username=f"p4_measure_{suffix}",
        email=f"p4_{suffix}@example.com",
        password=hash_password("measure-only"),
        role="candidate",
    )
    db.add(user)
    db.flush()

    resume_data = dict(case["resume"])
    resume = Resume(
        user_id=user.id,
        name=str(resume_data.get("name") or ""),
        file_name="p4_refeedback.txt",
        file_path="uploads/p4_refeedback.txt",
        file_type="txt",
        file_size=0,
        parsed_json=resume_data,
        is_deleted=0,
    )
    db.add(resume)
    db.flush()

    first_job: JobDescription | None = None
    for item in case["jobs"]:
        row = JobDescription(
            user_id=user.id,
            title=str(item["title"]),
            company=str(item.get("company") or ""),
            location=str(item.get("location") or ""),
            salary_range=str(item.get("salary_range") or ""),
            raw_text=str(item["title"]),
            parsed_json={"title": item["title"], "required_skills": list(item.get("required_skills") or [])},
            skill_tags=list(item.get("required_skills") or []),
            is_active=1,
        )
        db.add(row)
        db.flush()
        first_job = first_job or row

    db.add(
        InterviewSession(
            user_id=user.id,
            tenant_id=1,
            interview_type="tech",
            status="completed",
            evaluation_status="completed",
            completed_at=datetime(2026, 10, 1),
            evaluation=copy.deepcopy(case["interview"]),
        )
    )
    db.commit()
    if first_job is None:
        raise ValueError("夹具里没有岗位")
    return user, resume, first_job


def _summarize_rewrite(result: dict[str, Any] | None, prompt: str, weakness_texts: list[str]) -> dict[str, Any]:
    payload = result or {}
    suggestions = [row for row in (payload.get("suggestions") or []) if isinstance(row, dict)]
    combined = [f"{row.get('proposed_text') or ''} {row.get('reason') or ''}" for row in suggestions]
    return {
        "prompt_chars": len(prompt),
        "prompt_has_weakness": bool(weakness_texts) and all(text in prompt for text in weakness_texts),
        "prompt_has_untrusted_boundary": '<interview_profile data-role="untrusted">' in prompt,
        "suggestions": len(suggestions),
        "rejected": len(payload.get("rejected") or []),
        # 两个都是**代理指标**，只用来提示方向；质量由复核表上的人打分。
        "quantified": sum(1 for text in combined if re.search(r"\d", text)),
        "touches_weakness": sum(
            1 for text in combined if any(word in text for word in ("量化", "结构", "数据", "结果"))
        ),
        "items": suggestions[:5],
        "rejected_items": (payload.get("rejected") or [])[:5],
    }


def _summarize_career(
    result: dict[str, Any] | None,
    prompt: str,
    matched_gap_count: int,
    directions: list[Any],
) -> dict[str, Any]:
    payload = result or {}
    paths = [row for row in (payload.get("career_paths") or []) if isinstance(row, dict)]
    summary = str(payload.get("summary") or "")
    evidence_text = " ".join(
        str(item)
        for direction in directions
        for gap in (getattr(direction, "gap_skills", None) or [])
        for item in (gap.get("interview") or {}).get("evidence") or []
    )
    return {
        "prompt_chars": len(prompt),
        "prompt_has_evidence": bool(evidence_text) and ('"interview"' in prompt or evidence_text in prompt),
        "matched_gap_count": matched_gap_count,
        "paths": len(paths),
        "reason_source": payload.get("reason_source"),
        # 代理指标：模型有没有把证据带进理由/摘要；质量仍由复核表上的人打分。
        "cites_skill": sum(1 for row in paths if "Kafka" in str(row.get("reason") or "")),
        "cites_interview": sum(1 for row in paths if "面试" in str(row.get("reason") or "")),
        "summary_cites_interview": "面试" in summary,
        "items": [
            {
                "direction_key": row.get("direction_key"),
                "reason": row.get("reason"),
                "reason_source": row.get("reason_source"),
            }
            for row in paths[:5]
        ],
        "gap_evidence": [
            {"skill": gap.get("skill"), "interview": gap.get("interview")}
            for direction in directions
            for gap in (getattr(direction, "gap_skills", None) or [])
            if gap.get("interview")
        ][:5],
    }


def _trace_mark() -> int:
    session = SessionLocal()
    try:
        return int(session.query(func.max(PromptTrace.id)).scalar() or 0)
    finally:
        session.close()


def _trace_rows(since: int, sources: tuple[str, ...]) -> list[dict[str, Any]]:
    session = SessionLocal()
    try:
        rows = (
            session.query(PromptTrace)
            .filter(PromptTrace.id > since, PromptTrace.source.in_(sources))
            .order_by(PromptTrace.id.asc())
            .all()
        )
        return [
            {
                "id": row.id,
                "source": row.source,
                "prompt_version": row.prompt_version,
                "provider": row.provider,
                "model": row.model,
                "response_source": row.response_source,
                "degraded": bool(row.degraded),
                "status": row.status,
                "duration_ms": row.duration_ms,
                "total_tokens": row.total_tokens,
                "error_message": row.error_message,
            }
            for row in rows
        ]
    finally:
        session.close()


def measure_rewrite(
    db, case: dict[str, Any], user: User, resume: Resume, job: JobDescription, real: bool, pace_seconds: float = 0.0
) -> dict:
    service = resume_rewrite_service
    original = service.chat_json
    prompts: list[dict[str, str]] = []
    calls = {"n": 0}
    arm = {"name": "with_profile"}

    def recorded(prompt: str, **kwargs):
        calls["n"] += 1
        prompts.append({"arm": arm["name"], "prompt": prompt})
        return original(prompt, **kwargs) if real else MOCK_REWRITE

    service.chat_json = recorded
    try:
        with_profile = service.build_rewrite_suggestions(db, resume.id, jd_id=job.id, user_id=user.id)
        with_profile_source = "mock" if not real else str(get_llm_provenance().get("source") or "unknown")
        if pace_seconds:
            time.sleep(pace_seconds)
        arm["name"] = "control"
        control = service.build_rewrite_suggestions(db, resume.id, jd_id=job.id, user_id=None)
        control_source = "mock" if not real else str(get_llm_provenance().get("source") or "unknown")
    finally:
        service.chat_json = original
        service.set_llm_trace_context({})

    weakness_texts = [str(item).strip() for item in (case["interview"].get("weaknesses") or []) if str(item).strip()]
    prompt_by_arm = {row["arm"]: row["prompt"] for row in prompts}
    with_profile_summary = _summarize_rewrite(with_profile, prompt_by_arm.get("with_profile", ""), weakness_texts)
    with_profile_summary["llm_source"] = with_profile_source
    control_summary = _summarize_rewrite(control, prompt_by_arm.get("control", ""), weakness_texts)
    control_summary["llm_source"] = control_source
    return {
        "llm_calls": calls["n"],
        "weakness_texts": weakness_texts,
        "with_profile": with_profile_summary,
        "control": control_summary,
    }


def _mock_career(directions: list[Any]) -> dict[str, Any]:
    key = directions[0].key if directions else ""
    return {"career_paths": [{"direction_key": key, "reason": "mock 理由"}], "summary": "mock 摘要"}


def _career_recorder(prompts: list[str], original, directions: list[Any], real: bool, calls: dict[str, int]):
    def recorded(prompt: str, **kwargs):
        calls["n"] += 1
        prompts.append(prompt)
        return original(prompt, **kwargs) if real else _mock_career(directions)

    return recorded


def measure_career(db, case: dict[str, Any], user: User, resume: Resume, real: bool, pace_seconds: float = 0.0) -> dict:
    directions, corpus = derive_directions(db, case["resume"], user, limit=8)
    profile = public_profile(get_profile(db, user.id))
    arms: dict[str, Any] = {}
    calls = {"n": 0}

    for name, use_evidence in (("with_evidence", True), ("control", False)):
        if name == "control" and pace_seconds:
            time.sleep(pace_seconds)
        arm_directions = copy.deepcopy(directions)
        matched = attach_interview_evidence(arm_directions, profile if use_evidence else {})
        prompts: list[str] = []
        original = career_path_agent.chat_json
        career_path_agent.chat_json = _career_recorder(prompts, original, arm_directions, real, calls)
        try:
            result = career_path_agent.CareerPathAgent().recommend(case["resume"], arm_directions)
            source = "mock" if not real else str(get_llm_provenance().get("source") or "unknown")
        finally:
            career_path_agent.chat_json = original
        arms[name] = _summarize_career(result, prompts[0] if prompts else "", matched, arm_directions)
        arms[name]["llm_source"] = source

    return {"direction_count": len(directions), "corpus": corpus, "llm_calls": calls["n"], **arms}


def run_measurement(
    db, case: dict[str, Any], *, real: bool, arm: str = "all", pace_seconds: float = 0.0
) -> dict[str, Any]:
    user, resume, job = _seed(db, case)
    trace_since = _trace_mark() if real else None
    rewrite = measure_rewrite(db, case, user, resume, job, real, pace_seconds) if arm in ("all", "rewrite") else None
    career = measure_career(db, case, user, resume, real, pace_seconds) if arm in ("all", "career") else None
    sources = {"all": (REWRITE_SOURCE, CAREER_SOURCE), "rewrite": (REWRITE_SOURCE,), "career": (CAREER_SOURCE,)}[arm]
    traces = _trace_rows(trace_since, sources) if real else []
    return {
        "report_type": "p4_refeedback",
        "run_meta": {
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "fallback_model": settings.LLM_FALLBACK_MODEL,
            "mode": "real" if real else "mock",
            "arm": arm,
            "pace_seconds": pace_seconds,
            "generated_at": _now(),
            "fixture": str(FIXTURE.relative_to(ROOT)),
            "llm_calls": (rewrite or {}).get("llm_calls", 0) + (career or {}).get("llm_calls", 0),
            # trace.model 记的是**配置的主模型**；实际由哪条链路应答看 response_source。
            "response_sources": dict(Counter(row["response_source"] for row in traces)),
        },
        "rewrite": rewrite,
        "career": career,
        "traces": traces,
        "notes": [
            "rewrite 的两个数字（quantified / touches_weakness）是代理指标，不是质量分。",
            "career 量的是 /career-path/recommend 的 CareerPathAgent；orchestration 的 CareerAgent prompt 没有面试画像，不在本测量里。",
            "career 的 cites_skill / cites_interview 只看模型理由与摘要；mock 下 reason_source=rules，读数为 0 是预期的。",
            "质量请按复核表上的 0–3 分人工打分；本脚本不替人打分。",
        ],
    }


def _write_review(path: pathlib.Path, report: dict[str, Any]) -> None:
    meta = report["run_meta"]
    rewrite = report.get("rewrite")
    career = report.get("career")
    sources = meta.get("response_sources") or {}
    source_line = "；".join(f"{key} {value}" for key, value in sorted(sources.items())) or "（mock，无 provider 调用）"
    lines = [
        "# P4 回流测量复核表",
        "",
        f"- 模式：**{meta['mode']}**（配置 provider={meta['provider']} / model={meta['model']}"
        f" / fallback={meta.get('fallback_model') or '无'}）",
        f"- 有效来源：{source_line}（`trace.model` 是配置主模型，不代表实际链路）",
        f"- 生成：{meta['generated_at']}｜LLM 调用：{meta['llm_calls']}"
        f"｜臂间隔：{meta.get('pace_seconds') or 0:g}s",
        "- 评分：0=不可采纳/引入新事实；1=只改表达；2=针对弱点且不新增事实；3=针对弱点且把已有事实写得更可验证。",
        "",
    ]
    if rewrite is not None:
        lines += [
            "## 回流① 改写：带弱点提示 vs 对照",
            "",
            f"- 注入的弱点：{'；'.join(rewrite['weakness_texts']) or '（无）'}",
            "",
            "| 臂 | prompt 有弱点 | 建议 | 被拒 | 代理：带数字 | 代理：碰弱点 | 有效来源 |",
            "|---|---|---|---|---|---|---|",
        ]
        for key, label in (("with_profile", "带弱点"), ("control", "对照")):
            row = rewrite[key]
            lines.append(
                f"| {label} | {row['prompt_has_weakness']} | {row['suggestions']} | {row['rejected']} "
                f"| {row['quantified']} | {row['touches_weakness']} | {row.get('llm_source') or ''} |"
            )
        lines += ["", "### 带弱点这一臂的建议", ""]
        for item in rewrite["with_profile"]["items"]:
            lines += [
                f"- `{item.get('block_id')}`：{item.get('original')} → **{item.get('proposed_text')}**",
                f"  - 理由：{item.get('reason')}",
            ]
        lines += ["", "### 带弱点这一臂被拒的", ""]
        if rewrite["with_profile"]["rejected_items"]:
            for item in rewrite["with_profile"]["rejected_items"]:
                lines.append(f"- `{item.get('block_id')}`：{item.get('reason')}")
        else:
            lines.append("- （无）")
        lines += ["", "### 对照臂的建议", ""]
        for item in rewrite["control"]["items"]:
            lines += [
                f"- `{item.get('block_id')}`：{item.get('original')} → **{item.get('proposed_text')}**",
                f"  - 理由：{item.get('reason')}",
            ]
        lines += ["", "### 对照臂被拒的", ""]
        if rewrite["control"]["rejected_items"]:
            for item in rewrite["control"]["rejected_items"]:
                lines.append(f"- `{item.get('block_id')}`：{item.get('reason')}")
        else:
            lines.append("- （无）")

    scores = report.get("scores") or {}
    if scores and rewrite is not None:
        lines += [
            "",
            "## 回流① 初步评分（assistant-preliminary，非发布门）",
            "",
            f"- 评分人：{scores.get('annotator') or 'assistant-preliminary'}；待 zzh 复核/改分",
            "- 规则：0=不可采纳/引入新事实；1=只改表达；2=针对弱点且不新增事实；3=针对弱点且把已有事实写得更可验证。",
            "",
            "| 臂 | block_id | 分 | 依据 |",
            "|---|---|---|---|",
        ]
        for arm_key, label in (("with_profile", "带弱点"), ("control", "对照")):
            for row in scores.get(arm_key) or []:
                lines.append(f"| {label} | `{row.get('block_id')}` | {row.get('score')} | {row.get('note') or ''} |")
        totals = scores.get("totals") or {}
        if totals:
            lines += [
                "",
                f"- 合计：带弱点 **{totals.get('with_profile')}** / 对照 **{totals.get('control')}**（单条 0–3）。",
            ]

    if career is not None:
        lines += [
            "",
            "## 回流② 职业方向：带面试证据 vs 对照（CareerPathAgent）",
            "",
            f"- 贴上的证据：{json.dumps(career['with_evidence']['gap_evidence'], ensure_ascii=False)}",
            "",
            "| 臂 | 贴上的缺口 | prompt 有证据 | 方向数 | reason_source | 理由点名 Kafka | 理由提面试 | 有效来源 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for key, label in (("with_evidence", "带证据"), ("control", "对照")):
            row = career[key]
            lines.append(
                f"| {label} | {row['matched_gap_count']} | {row['prompt_has_evidence']} | {row['paths']} "
                f"| {row['reason_source']} | {row['cites_skill']} | {row['cites_interview']} "
                f"| {row.get('llm_source') or ''} |"
            )
        lines += ["", "### 带证据这一臂的理由", ""]
        for item in career["with_evidence"]["items"]:
            lines.append(f"- `{item.get('direction_key')}`：{item.get('reason')}（{item.get('reason_source')}）")
        lines += ["", "### 对照臂的理由", ""]
        for item in career["control"]["items"]:
            lines.append(f"- `{item.get('direction_key')}`：{item.get('reason')}（{item.get('reason_source')}）")
    lines += ["", "> 代理指标只提示方向；采纳哪一条由人按上面的 0–3 分判。", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P4 回流测量（默认 mock，零花费）")
    parser.add_argument("--allow-real", action="store_true", help="调用真 provider（按 --arm 4/2 发，花钱）")
    parser.add_argument("--arm", choices=("all", "rewrite", "career"), default="all", help="只跑某一臂")
    parser.add_argument("--pace-seconds", type=float, default=0.0, help="两臂之间的间隔（秒）")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--review", default=str(DEFAULT_REVIEW))
    args = parser.parse_args(argv)

    require_mock("measure_p4_refeedback.py", allow_real=args.allow_real)
    if engine.url.get_backend_name() != "sqlite":
        raise SystemExit(f"拒绝在 {engine.url} 上跑：这条测量只许进程内 sqlite")
    Base.metadata.create_all(bind=engine)

    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        report = run_measurement(db, case, real=args.allow_real, arm=args.arm, pace_seconds=args.pace_seconds)
    finally:
        db.close()

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    _write_review(pathlib.Path(args.review), report)

    print(f"p4_refeedback {report['run_meta']['mode']}｜arm={args.arm}")
    if report["rewrite"] is not None:
        rewrite = report["rewrite"]
        print(
            f"  rewrite 提示 {rewrite['with_profile']['prompt_has_weakness']} vs {rewrite['control']['prompt_has_weakness']}"
            f"｜建议 {rewrite['with_profile']['suggestions']} vs {rewrite['control']['suggestions']}"
        )
    if report["career"] is not None:
        career = report["career"]
        print(
            f"  career 贴缺口 {career['with_evidence']['matched_gap_count']} vs {career['control']['matched_gap_count']}"
            f"｜证据进 prompt {career['with_evidence']['prompt_has_evidence']} vs {career['control']['prompt_has_evidence']}"
        )
    print(f"report {output}")
    print(f"review {args.review}")
    if report["run_meta"]["mode"] != "real":
        print("mock：仪器可跑，质量数字要 --allow-real 那一发。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
