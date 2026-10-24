import json

from scripts.gen_interview_quality_sample import CASES, OUTPUT, main, render


def test_sheet_has_one_row_per_tier_and_question():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    text = OUTPUT.read_text(encoding="utf-8")

    for tier in ("good", "mid", "weak"):
        assert text.count(f"| {tier} |") == len(cases["questions"])
    assert "介绍一个你最有成就感的项目" in text
    assert "追问（跑完粘贴）" in text


def test_check_mode_is_current():
    assert main(["--check"]) == 0


def test_render_fills_followups_from_a_report():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    text = render(cases, {("good", 1): "追问A", ("weak", 6): "追问B"})

    assert "追问A" in text
    assert "追问B" in text
    assert "| good | 1 | project |" in text
