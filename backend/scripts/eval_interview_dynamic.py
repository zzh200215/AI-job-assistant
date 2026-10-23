"""P3.2 动态 vs 静态对比跑者：三档脚本化考生 × 两臂（决策器开/关）。

这一格量的是**选题与追问**，不是模型打分质量：三档考生的分数写死在用例里，两臂吃同一份分数。
因此：

- **弱点命中率**（本跑者的主指标）：JD 必考技能里，有多少个**出现在了某一题的题面上**。
  静态臂只有那 6 道 starter，题面里不含 JD 词表 ⇒ 覆盖应接近 0；动态臂在答得差时按
  "还没考到的必考项"追问 ⇒ 覆盖应上去。门槛默认 **动态 ≥ 静态 + 20pp**（原稿那格）。
- **零额外等待率**：不带 `is_follow_up` 的题（= 从候选池直接出）占全部出题的比例。原稿目标 75%。
  **只对 good 那一档设门槛**：弱档本来就会触发更多追问，拿它去撞 75% 是把设计目标当普适指标。
- **区分度**：脚本化评分下三档总分差是**构造出来的**，两臂必然相同。这里只如实打印，不设门；
  真正的区分度要等真 provider 那一发。

跑法（默认 mock、零花费）：
    python scripts/eval_interview_dynamic.py
    python scripts/eval_interview_dynamic.py --output reports/interview_dynamic_latest.json
真 provider 必须显式 `--allow-real`，且要清楚：每一句追问都会真的打一次模型。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402, F401  注册全部表
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.interview_session import InterviewSession  # noqa: E402
from app.services.interview_engine import InterviewEngine  # noqa: E402
from app.services.interviewer_decision import DEEPEN_SCORE_CEILING  # noqa: E402
from scripts.provider_guard import require_mock  # noqa: E402

CASES = pathlib.Path("tests/eval/interview_dynamic_cases.json")


@compiles(BigInteger, "sqlite")
def _compile_big_integer_sqlite(_type, _compiler, **_kwargs):
    # 必须在任何建表之前挂上：SQLite 只有 INTEGER PRIMARY KEY 才自增（见 conftest 的注释）。
    return "INTEGER"


def _make_session(skills: list[str], questions: list[dict[str, str]]) -> Session:  # noqa: F821
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    session = InterviewSession(
        user_id=1,
        resume_id=1,
        jd_id=1,
        interview_type="tech",
        status="created",
        questions=questions,
        messages=[],
        evaluation={},
        memory_snapshot={
            "question_generation": {"status": "pending"},
            "jd_required_skills": list(skills),
        },
        total_questions=len(questions),
        answered_count=0,
    )
    db.add(session)
    db.commit()
    return db, session


def _scripted_evaluator(score: int):
    def evaluate(_question: str, _ref: str, _answer: str) -> dict:
        return {
            "completeness": score,
            "accuracy": score,
            "depth": score,
            "expression": score,
            "overall_score": score,
            "feedback": "脚本化评分",
            "improvement": "脚本化评分，不参与本条结论",
            "follow_up": False,
            "evidence": [],
        }

    return evaluate


def run_arm(cases: dict, tier_name: str, dynamic: bool, pace_seconds: float = 0.0) -> dict:
    skills = list(cases["jd"]["required_skills"])
    questions = [
        {
            "id": index,
            "question": item["question"],
            "category": item["category"],
            "ref_answer": item["ref_answer"],
        }
        for index, item in enumerate(cases["questions"])
    ]
    tier = cases["candidates"][tier_name]

    settings.INTERVIEW_USE_DECIDER = dynamic
    db, session = _make_session(skills, questions)
    engine = InterviewEngine(session.id)
    engine.db = db
    engine.session = session
    engine._evaluate_answer = _scripted_evaluator(int(tier["score"]))

    decision_calls = {"n": 0, "ms": 0.0, "max_ms": 0.0}
    real_decision_chat = engine._decision_chat

    def counted_chat():
        inner = real_decision_chat()

        def call(prompt: str):
            # 连打 12 发会撞 provider 的短时限流；间隔不进入 decision_ms，只把调用摊开。
            # 默认 0 保持原行为；真 provider 想拿干净单发延迟时再显式传 --pace-seconds。
            if pace_seconds > 0:
                time.sleep(pace_seconds)
            started = time.monotonic()
            try:
                return inner(prompt)
            finally:
                elapsed = (time.monotonic() - started) * 1000
                decision_calls["n"] += 1
                decision_calls["ms"] += elapsed
                decision_calls["max_ms"] = max(decision_calls["max_ms"], elapsed)

        return call

    engine._decision_chat = counted_chat

    emitted: list[dict] = []
    payload = engine.start()
    guard = 0
    while payload and payload.get("type") not in {"finished", "end"} and guard < 40:
        guard += 1
        emitted.append(payload)
        is_followup = bool((payload.get("metadata") or {}).get("is_follow_up"))
        answer = tier["followup_answer"] if is_followup else tier["answer"]
        payload = engine.handle_answer(answer)

    texts = [str(item.get("content") or "") for item in emitted]
    covered = sorted({skill for skill in skills if any(skill in text for text in texts)})
    followups = [item for item in emitted if (item.get("metadata") or {}).get("is_follow_up")]
    pool_questions = [item for item in emitted if not (item.get("metadata") or {}).get("is_follow_up")]
    db.close()

    return {
        "tier": tier_name,
        "arm": "dynamic" if dynamic else "static",
        "questions_emitted": len(emitted),
        "followups": len(followups),
        "decision_llm_calls": decision_calls["n"],
        "decision_ms_total": round(decision_calls["ms"], 1),
        "decision_ms_avg": round(decision_calls["ms"] / decision_calls["n"], 1) if decision_calls["n"] else None,
        "decision_ms_max": round(decision_calls["max_ms"], 1) if decision_calls["n"] else None,
        "decision_composed": sum(
            1 for item in followups if ((item.get("metadata") or {}).get("decision") or {}).get("source") == "llm"
        ),
        "decision_degraded": sum(
            1 for item in followups if bool(((item.get("metadata") or {}).get("decision") or {}).get("degraded"))
        ),
        "covered_skills": covered,
        "coverage_rate": round(len(covered) / len(skills), 4) if skills else 0.0,
        "zero_wait_rate": round(len(pool_questions) / len(emitted), 4) if emitted else 0.0,
        "score_total": int(tier["score"]) * len(emitted),
        "transcript": [
            {
                "round": (item.get("metadata") or {}).get("round"),
                "is_follow_up": bool((item.get("metadata") or {}).get("is_follow_up")),
                "content": item.get("content"),
                "decision": (item.get("metadata") or {}).get("decision"),
            }
            for item in emitted
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument("--output", default=None)
    parser.add_argument("--allow-real", action="store_true")
    parser.add_argument("--min-gap-gain-pp", type=float, default=20.0)
    parser.add_argument("--min-zero-wait", type=float, default=0.75)
    parser.add_argument(
        "--pace-seconds",
        type=float,
        default=0.0,
        help="每次决策模型调用前的间隔；真 provider 连打会撞 429，单发延迟不含这段 sleep",
    )
    args = parser.parse_args()

    provider = require_mock("eval_interview_dynamic.py", allow_real=args.allow_real)
    cases = json.loads(pathlib.Path(args.cases).read_text(encoding="utf-8"))

    runs = {}
    for tier_name in cases["candidates"]:
        runs[tier_name] = {
            "static": run_arm(cases, tier_name, dynamic=False, pace_seconds=args.pace_seconds),
            "dynamic": run_arm(cases, tier_name, dynamic=True, pace_seconds=args.pace_seconds),
        }

    gains = {}
    for tier_name, pair in runs.items():
        static_rate = pair["static"]["coverage_rate"]
        dynamic_rate = pair["dynamic"]["coverage_rate"]
        gains[tier_name] = round((dynamic_rate - static_rate) * 100, 1)

    # 增益只对**有缺口可补**的档设门：强档每答都对，本来就不该触发追问，拿它的 0pp 撞门
    # 等于把设计目标当普适指标。低于深挖阈值的档才参与增益判定。
    gated_tiers = [name for name in cases["candidates"] if cases["candidates"][name]["score"] < DEEPEN_SCORE_CEILING]
    worst_gain = min(gains[name] for name in gated_tiers) if gated_tiers else 0.0
    good_zero_wait = runs["good"]["dynamic"]["zero_wait_rate"]
    errors = [
        f"{tier}/{arm}: 出题数为 0"
        for tier, pair in runs.items()
        for arm, result in pair.items()
        if result["questions_emitted"] == 0
    ]
    failures = list(errors)
    if worst_gain < args.min_gap_gain_pp:
        failures.append(f"弱点命中率增益 {worst_gain}pp < 门槛 {args.min_gap_gain_pp}pp")
    if good_zero_wait < args.min_zero_wait:
        failures.append(f"good 档零额外等待 {good_zero_wait:.2%} < 门槛 {args.min_zero_wait:.0%}")

    report = {
        "report_type": "interview_dynamic",
        "run_meta": {
            "provider": provider,
            "model": settings.LLM_MODEL,
            "cases": args.cases,
            "pace_seconds": args.pace_seconds,
            "gates": {
                "min_gap_gain_pp": args.min_gap_gain_pp,
                "min_zero_wait": args.min_zero_wait,
                "zero_wait_applies_to": "good",
            },
        },
        "gap_gain_pp": gains,
        "runs": runs,
        "failures": failures,
        "notes": {
            "distinctness": "脚本化评分下三档总分差是构造性的，两臂相同；真区分度要等真 provider。",
            "coverage": "覆盖 = JD 必考技能名出现在某题题面上；静态臂题面不含 JD 词表。",
        },
    }

    if args.output:
        target = pathlib.Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[写入] {target}")

    print(f"provider={provider}  cases={args.cases}")
    for tier_name, pair in runs.items():
        print(
            f"  {tier_name:5s} static={pair['static']['coverage_rate']:.2f}/{pair['static']['questions_emitted']}问 "
            f"dynamic={pair['dynamic']['coverage_rate']:.2f}/{pair['dynamic']['questions_emitted']}问 "
            f"增益={gains[tier_name]:+.1f}pp 零等待={pair['dynamic']['zero_wait_rate']:.0%} "
            f"决策调用={pair['dynamic']['decision_llm_calls']} "
            f"真组织={pair['dynamic']['decision_composed']} 降级={pair['dynamic']['decision_degraded']}"
        )
    if failures:
        for item in failures:
            print(f"[红] {item}")
        return 3
    print("[ok] 弱点命中率增益与 good 档零额外等待都在门槛内")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
