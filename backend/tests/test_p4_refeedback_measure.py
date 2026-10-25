"""P4 回流测量的仪器自检：mock 下两臂必须只差一个变量。"""

from __future__ import annotations

import json
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts import measure_p4_refeedback as measure  # noqa: E402


def _case() -> dict:
    return json.loads(measure.FIXTURE.read_text(encoding="utf-8"))


def test_fixture_shape_is_what_the_two_arms_need():
    case = _case()
    resume = case["resume"]

    assert {"Python", "FastAPI"} <= set(resume["skills"])
    assert any(word in " ".join(case["interview"]["weaknesses"]) for word in ("量化", "结构"))
    titles = {job["title"] for job in case["jobs"]}
    assert len(case["jobs"]) >= 2 and len(titles) == 1, "同一方向至少两条岗位，derive_directions 才成立"
    assert all("Kafka" in job["required_skills"] for job in case["jobs"])
    assert case["interview"]["interview_memory"]["jd_required_skills"] == ["Kafka"]


def test_mock_measurement_shows_the_two_arms_differ_only_by_the_profile(db_session):
    report = measure.run_measurement(db_session, _case(), real=False)

    assert report["run_meta"]["mode"] == "mock"
    assert report["run_meta"]["arm"] == "all"
    assert report["run_meta"]["pace_seconds"] == 0.0
    assert report["run_meta"]["llm_calls"] == 4

    rewrite = report["rewrite"]
    assert rewrite["with_profile"]["prompt_has_weakness"] is True
    assert rewrite["with_profile"]["prompt_has_untrusted_boundary"] is True
    assert rewrite["control"]["prompt_has_weakness"] is False
    # 边界标签两臂都在（模板固定包着 hint）；control 的边界里是"无；按通用…"这句。
    assert rewrite["control"]["prompt_has_untrusted_boundary"] is True
    assert rewrite["with_profile"]["suggestions"] == 1
    assert rewrite["with_profile"]["llm_source"] == "mock"
    assert rewrite["control"]["llm_source"] == "mock"

    career = report["career"]
    assert career["with_evidence"]["matched_gap_count"] >= 1
    assert career["control"]["matched_gap_count"] == 0
    assert career["with_evidence"]["prompt_has_evidence"] is True
    assert career["control"]["prompt_has_evidence"] is False
    assert career["with_evidence"]["paths"] == career["control"]["paths"] == 1
    assert career["with_evidence"]["llm_source"] == "mock"


def test_rewrite_proxies_count_digits_and_weakness_words():
    payload = {
        "suggestions": [
            {"proposed_text": "把 P99 延迟下降 35%", "reason": "补量化"},
            {"proposed_text": "经历写清楚", "reason": "结构更清晰"},
        ],
        "rejected": [{"reason": "unanchored"}],
    }

    summary = measure._summarize_rewrite(payload, "prompt 成果未量化", ["成果未量化"])

    assert summary["suggestions"] == 2
    assert summary["rejected"] == 1
    assert summary["quantified"] == 1
    assert summary["touches_weakness"] == 2
    assert summary["prompt_has_weakness"] is True


def test_career_proxies_count_evidence_mentions():
    class Direction:
        gap_skills = [{"skill": "Kafka", "interview": {"evidence": ["只说了 at-least-once"]}}]

    payload = {
        "career_paths": [
            {"direction_key": "a", "reason": "上次面试 Kafka 只说了 at-least-once，建议先补幂等。"},
            {"direction_key": "b", "reason": "岗位匹配度较高。"},
        ],
        "summary": "上次面试留下的短板已标在缺口上。",
        "reason_source": "model",
    }

    summary = measure._summarize_career(payload, '{"interview": "只说了 at-least-once"}', 1, [Direction()])

    assert summary["prompt_has_evidence"] is True
    assert summary["cites_skill"] == 1
    assert summary["cites_interview"] == 1
    assert summary["summary_cites_interview"] is True
    assert summary["matched_gap_count"] == 1


def test_rewrite_only_skips_the_career_arm(tmp_path, db_session):
    report = measure.run_measurement(db_session, _case(), real=False, arm="rewrite")

    assert report["rewrite"] is not None
    assert report["career"] is None
    assert report["run_meta"]["arm"] == "rewrite"
    assert report["run_meta"]["llm_calls"] == 2

    target = tmp_path / "review.md"
    measure._write_review(target, report)
    text = target.read_text(encoding="utf-8")
    assert "回流①" in text
    assert "回流②" not in text


def test_review_sheet_has_both_arms(tmp_path, db_session):
    report = measure.run_measurement(db_session, _case(), real=False)
    report["scores"] = {
        "annotator": "assistant-preliminary",
        "with_profile": [{"block_id": "self_evaluation", "score": 2, "note": "复核用"}],
        "control": [{"block_id": "self_evaluation", "score": 1, "note": "复核用"}],
        "totals": {"with_profile": 2, "control": 1},
    }

    target = tmp_path / "review.md"
    measure._write_review(target, report)
    text = target.read_text(encoding="utf-8")

    assert "带弱点" in text and "对照" in text
    assert "带证据" in text and "贴上的缺口" in text
    assert "有效来源" in text
    assert "初步评分" in text and "assistant-preliminary" in text
    assert "| 带弱点 | `self_evaluation` | 2 |" in text
    assert "0–3 分" in text
