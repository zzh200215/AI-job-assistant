from scripts.measure_file_extraction import normalize, summarize


def test_summarize_groups_by_type_and_counts_failures():
    details = [
        {"file_type": "pdf", "ok": True, "chars": 10, "exact": True, "normalized": True, "error": ""},
        {"file_type": "pdf", "ok": False, "chars": 0, "exact": False, "normalized": False, "error": "ValueError: x"},
        {"file_type": "docx", "ok": True, "chars": 20, "exact": True, "normalized": True, "error": ""},
    ]

    summary = summarize(details)

    assert summary["pdf"]["files"] == 2
    assert summary["pdf"]["ok"] == 1
    assert summary["pdf"]["failed"] == 1
    assert summary["pdf"]["exact"] == 1
    assert summary["pdf"]["errors"] == ["ValueError: x"]
    assert summary["pdf"]["chars_median"] == 10
    assert summary["docx"]["files"] == 1
    assert summary["docx"]["chars_median"] == 20


def test_normalize_ignores_whitespace():
    assert normalize(" a \n b\t") == "ab"
