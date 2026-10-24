import json
from pathlib import Path

from scripts.eval_interview_dynamic import answer_for

CASES = Path(__file__).parent / "eval" / "interview_dynamic_cases.json"


def test_cases_have_one_distinct_answer_per_question():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    count = len(cases["questions"])
    for name, tier in cases["candidates"].items():
        assert len(tier["answers"]) == count, name
        assert len(tier["followup_answers"]) == count, name
        assert len(set(tier["answers"])) == count, f"{name} 的答案在题间重复"
        assert len(set(tier["followup_answers"])) == count, f"{name} 的追问答案在题间重复"
        assert all(str(item).strip() for item in tier["answers"] + tier["followup_answers"]), name


def test_the_same_question_has_a_distinct_answer_in_each_tier():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    for index in range(len(cases["questions"])):
        answers = {cases["candidates"][tier]["answers"][index] for tier in ("good", "mid", "weak")}
        assert len(answers) == 3, f"第 {index + 1} 题三档答案重复"


def test_answer_for_picks_the_round_and_falls_back_to_a_single_answer():
    tier = {"answers": ["a1", "a2", "a3"], "followup_answers": ["f1", "f2", "f3"]}
    assert answer_for(tier, 3, 1, False) == "a1"
    assert answer_for(tier, 3, 2, False) == "a2"
    assert answer_for(tier, 3, 3, True) == "f3"
    assert answer_for(tier, 3, 9, False) == "a3"

    legacy = {"answer": "legacy", "followup_answer": "legacy-followup"}
    assert answer_for(legacy, 3, 2, False) == "legacy"
    assert answer_for(legacy, 3, 2, True) == "legacy-followup"
