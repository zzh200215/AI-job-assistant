import hashlib
import json
import re

from scripts.gen_gold_worksheet import EVAL_DIR, OUTPUT_PATH, TEMPLATE_PATH, main


def _seed_from_html() -> dict:
    html = OUTPUT_PATH.read_text(encoding="utf-8")
    match = re.search(r'<script id="seed-data" type="application/json">(.*?)</script>', html, re.S)
    assert match, "worksheet 里没有 seed-data"
    return json.loads(match.group(1))


def test_worksheet_seed_matches_template_and_sources():
    seed = _seed_from_html()
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    assert seed["template"] == template
    for row in template["rows"]:
        source = (EVAL_DIR / row["source_file"]).read_text(encoding="utf-8")
        assert seed["texts"][row["id"]] == source
        assert seed["sources"][row["id"]]["sha256"] == hashlib.sha256(source.encode("utf-8")).hexdigest()


def test_worksheet_is_self_contained():
    html = OUTPUT_PATH.read_text(encoding="utf-8")
    shell = re.sub(r'<script id="seed-data".*?</script>', "", html, flags=re.S)

    assert "<script src=" not in shell
    assert "<link " not in shell
    assert "fetch(" not in shell


def test_check_mode_is_current():
    assert main(["--check"]) == 0
