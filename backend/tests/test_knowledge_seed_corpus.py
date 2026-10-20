from pathlib import Path

from app.core.config import settings
from app.services.chunk_service import chunk_document
from app.services.interview_question_source import CONTEXT_SNIPPET_CHARS
from scripts.import_knowledge_seeds import (
    ENTRY_COUNT_RANGE,
    ENTRY_FIELDS,
    MAX_ENTRY_CHARS,
    STRUCTURED_SUBDIR,
    iter_structured_files,
    parse_seed_entries,
    validate_seed_corpus,
)

EXPECTED_ROLE_FAMILIES = {
    "interview_q": {"后端", "前端", "数据", "AI", "DevOps", "产品", "行为"},
    "skill_model": {
        "后端工程师",
        "前端工程师",
        "数据工程师",
        "AI 应用工程师",
        "DevOps 工程师",
        "SRE",
        "产品经理",
        "测试工程师",
        "安全工程师",
        "数据分析师",
        "数据科学家",
        "通用工程素养",
        "通用职级梯度",
    },
}


def _seed_files(category: str) -> list[Path]:
    files = iter_structured_files(category)
    assert files, f"{category} has no files under {STRUCTURED_SUBDIR}/"
    return files


def _entries(category: str) -> list[dict]:
    entries = []
    for path in _seed_files(category):
        for entry in parse_seed_entries(path.read_text(encoding="utf-8")):
            entry["file"] = path.name
            entries.append(entry)
    return entries


def test_seed_corpus_passes_shape_gates():
    report = validate_seed_corpus()

    assert report["ok"] is True, report["errors"]
    assert report["max_entry_chars"] <= MAX_ENTRY_CHARS
    assert report["max_chunk_chars"] <= CONTEXT_SNIPPET_CHARS


def test_each_category_has_20_to_30_structured_entries():
    low, high = ENTRY_COUNT_RANGE

    for category in ENTRY_FIELDS:
        entries = _entries(category)
        assert low <= len(entries) <= high, f"{category}: {len(entries)} entries"


def test_entries_have_required_fields_and_unique_headings():
    for category, required_fields in ENTRY_FIELDS.items():
        headings = set()
        questions = set()
        for entry in _entries(category):
            heading = entry["heading"]
            assert "｜" in heading, heading
            assert heading not in headings, f"duplicate heading: {heading}"
            headings.add(heading)
            for field in required_fields:
                assert entry["fields"].get(field), f"{category}/{heading} missing {field}"
            question = entry["fields"].get("题目")
            if question:
                assert question not in questions, f"duplicate question: {question}"
                questions.add(question)


def test_each_entry_and_chunk_fits_prompt_window():
    for category in ENTRY_FIELDS:
        for entry in _entries(category):
            assert len(entry["text"]) <= MAX_ENTRY_CHARS, entry["heading"]
        for path in _seed_files(category):
            chunks = chunk_document(
                path.read_text(encoding="utf-8"),
                chunk_size=settings.RAG_CHUNK_SIZE,
                overlap=settings.RAG_CHUNK_OVERLAP,
            )
            assert chunks, path.name
            for chunk in chunks:
                assert len(chunk["text"]) <= CONTEXT_SNIPPET_CHARS, f"{path.name} chunk {chunk['index']}"


def test_seed_corpus_covers_expected_role_families():
    for category, expected in EXPECTED_ROLE_FAMILIES.items():
        families = {entry["heading"].split("｜", 1)[0].strip() for entry in _entries(category)}
        assert expected <= families, f"{category} missing: {sorted(expected - families)}"


def test_shape_gate_bites_on_malformed_seed(tmp_path):
    folder = tmp_path / "interview_q" / "role_families"
    folder.mkdir(parents=True)
    (folder / "title_only.md").write_text("# 只有标题\n", encoding="utf-8")
    (folder / "missing_field.md").write_text("## 后端｜缺字段\n\n- 题目：只写了一行\n", encoding="utf-8")
    (folder / "too_long.md").write_text(f"## 后端｜太长\n\n- 题目：{'长' * 300}\n", encoding="utf-8")

    report = validate_seed_corpus(tmp_path)
    errors = "\n".join(report["errors"])

    assert report["ok"] is False
    assert "title_only.md: no `##` entries" in errors
    assert "missing_field.md: missing field" in errors
    assert "too_long.md" in errors and "limit" in errors


def test_check_mode_is_offline_and_green():
    from scripts.import_knowledge_seeds import main

    assert main(["--check"]) == 0
