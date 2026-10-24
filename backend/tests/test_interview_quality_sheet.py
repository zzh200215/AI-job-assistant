import json
import re

from scripts.gen_interview_quality_sheet import CASES, OUTPUT, build_seed, main


def _seed() -> dict:
    html = OUTPUT.read_text(encoding="utf-8")
    match = re.search(r'<script id="seed-data" type="application/json">(.*?)</script>', html, re.S)
    assert match, "sheet 里没有 seed-data"
    return json.loads(match.group(1))


def test_sheet_seed_matches_cases():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    seed = _seed()

    assert len(seed["rows"]) == 3 * len(cases["questions"])
    assert seed["rows"][0]["question"] == cases["questions"][0]["question"]
    for tier in ("good", "mid", "weak"):
        assert sum(1 for row in seed["rows"] if row["tier"] == tier) == len(cases["questions"])


def test_sheet_is_self_contained():
    html = OUTPUT.read_text(encoding="utf-8")
    shell = re.sub(r'<script id="seed-data".*?</script>', "", html, flags=re.S)

    assert "<script src=" not in shell
    assert "<link " not in shell
    assert "fetch(" not in shell


def test_check_mode_is_current():
    assert main(["--check"]) == 0


def test_seed_fills_followups_from_a_report():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    seed = build_seed(cases, {("good", 1): "追问A"})

    assert seed["rows"][0]["followup"] == "追问A"
    assert seed["rows"][1]["followup"] == ""
