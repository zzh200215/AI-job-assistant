"""抽取臂的判据：文件拆出来的文本必须就是 eval 的输入，坏 PDF 必须给出用户可见的报错。"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.utils.file_parser import parse_resume  # noqa: E402
from scripts.eval_parse import check_thresholds, extraction_arm, load_eval_set  # noqa: E402

EVAL_SET = BACKEND / "tests/eval/parse_eval.jsonl"
FIXTURES = BACKEND / "tests/eval/resume_files"


def test_broken_pdf_returns_the_user_facing_message_not_the_library_one():
    """真文件 `b2fe2b49….pdf` 的底层说法是 `No /Root object! - Is this really a PDF?`，
    以前它落到泛化的"PDF 解析失败"分支，用户会看到英文异常名。"""
    with pytest.raises(ValueError) as exc:
        parse_resume(str(FIXTURES / "broken.pdf"), "pdf")

    message = str(exc.value)
    assert "PDF 文件格式异常或已损坏" in message
    assert "No /Root object" not in message


def test_extraction_arm_matches_fixtures_and_real_source_files():
    rows = load_eval_set(EVAL_SET)
    result = extraction_arm(rows, FIXTURES / "manifest.json", EVAL_SET)

    assert result["cases"] == 8, "4 条清单夹具 + 4 条真文本来源"
    assert result["matched"] == 8
    assert result["match_rate"] == 1.0
    assert result["errors"] == []

    by_id = {detail["id"]: detail for detail in result["details"]}
    assert by_id["txt_zh"]["exact"] is True
    assert by_id["docx_zh_roundtrip"]["normalized"] is True
    assert by_id["pdf_ascii_roundtrip"]["normalized"] is True
    assert by_id["broken_pdf"]["ok"] is True
    real = [detail for detail in result["details"] if detail["source"] == "real"]
    assert len(real) == 4
    assert all(detail["exact"] for detail in real), "真文本夹具与语料 raw_text 必须逐字相同"


def test_extraction_arm_reports_a_mismatch_instead_of_passing_it(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "expect.txt").write_text("world", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "bad", "file": "a.txt", "file_type": "txt", "expect": "text", "expect_text": "expect.txt"}
                ]
            }
        ),
        encoding="utf-8",
    )

    result = extraction_arm([], manifest, EVAL_SET)

    assert result["match_rate"] == 0.0
    assert any("bad" in item and "不一致" in item for item in result["errors"]), result["errors"]


def test_a_missing_source_file_is_an_error_not_a_skip():
    rows = [{"id": "ghost", "kind": "real", "source_file": "nope.txt", "raw_text": "x"}]
    result = extraction_arm(rows, FIXTURES / "manifest.json", EVAL_SET)

    assert any("ghost" in item and "源文件不存在" in item for item in result["errors"]), result["errors"]


def _det() -> dict:
    return {"errors": [], "tail_keep_rate": 1.0}


def test_extraction_mismatch_is_gated():
    bad = check_thresholds(
        _det(),
        None,
        mock=True,
        max_errors=0,
        min_tail_keep=None,
        min_structure_rate=None,
        min_field_f1=None,
        extraction={"cases": 2, "match_rate": 0.5, "errors": ["x: 不一致"]},
        min_extract_match=1.0,
    )

    assert any("抽取臂不符" in item for item in bad)
    assert any("抽取一致率" in item for item in bad)


def test_clean_extraction_leaves_the_gate_green():
    bad = check_thresholds(
        _det(),
        None,
        mock=True,
        max_errors=0,
        min_tail_keep=None,
        min_structure_rate=None,
        min_field_f1=None,
        extraction={"cases": 2, "match_rate": 1.0, "errors": []},
        min_extract_match=1.0,
    )

    assert not any("抽取" in item for item in bad), bad
