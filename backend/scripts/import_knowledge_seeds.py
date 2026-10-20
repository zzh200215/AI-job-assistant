#!/usr/bin/env python
"""Import the bundled knowledge seed documents.

Structured role-family seeds live under `<category>/role_families/` and use one
`##` heading per entry. `--check` validates that corpus without touching the
database or calling the embedding provider.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.chunk_service import chunk_document  # noqa: E402
from app.services.interview_question_source import CONTEXT_SNIPPET_CHARS  # noqa: E402

SEED_ROOT = ROOT.parent / "docs" / "knowledge-seeds"
IMPORT_SCRIPT = ROOT / "scripts" / "import_knowledge.py"

STRUCTURED_SUBDIR = "role_families"
ENTRY_FIELDS = {
    "interview_q": ("题目", "考察点", "参考要点", "追问"),
    "skill_model": ("核心能力", "典型证据", "评估锚点", "常见短板"),
}
ENTRY_COUNT_RANGE = (20, 30)
MIN_ROLE_FAMILIES = 6
MAX_ENTRY_CHARS = 250

SEED_MAPPINGS = [
    ("resume_template", "resume_template"),
    ("jd_lib", "jd_lib"),
    ("interview_q", "interview_q"),
    ("skill_model", "skill_model"),
    ("industry_report", "industry_report"),
    ("career_path", "career_path"),
    ("salary_market", "salary_market"),
    ("transition_guide", "transition_guide"),
]


def iter_structured_files(category: str, seed_root: Path = SEED_ROOT) -> list[Path]:
    return sorted(path for path in (seed_root / category / STRUCTURED_SUBDIR).glob("*.md") if path.is_file())


def parse_seed_entries(text: str) -> list[dict]:
    """Split a structured seed file into `##` entries and their `- 字段：值` lines."""
    entries: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
            current = {"heading": line[3:].strip(), "fields": {}, "lines": [line]}
            continue
        if current is None:
            continue
        current["lines"].append(line)
        stripped = line.strip()
        if stripped.startswith("- ") and "：" in stripped:
            label, value = stripped[2:].split("：", 1)
            current["fields"][label.strip()] = value.strip()
    if current is not None:
        entries.append(current)
    for entry in entries:
        entry["text"] = "\n".join(entry.pop("lines")).strip()
    return entries


def _role_family(heading: str) -> str:
    return heading.split("｜", 1)[0].strip() if "｜" in heading else ""


def validate_seed_corpus(seed_root: Path | None = None) -> dict:
    """Validate the structured role-family corpus; no DB session, no embedding calls."""
    root = seed_root or SEED_ROOT
    report: dict = {"ok": True, "errors": [], "categories": {}, "max_entry_chars": 0, "max_chunk_chars": 0}

    for category, required_fields in ENTRY_FIELDS.items():
        files = iter_structured_files(category, root)
        category_errors: list[str] = []
        entries: list[dict] = []
        headings: set[str] = set()
        questions: set[str] = set()
        families: set[str] = set()
        max_chunk_chars = 0

        if not files:
            category_errors.append(f"{category}: no structured files under {STRUCTURED_SUBDIR}/")

        for path in files:
            text = path.read_text(encoding="utf-8")
            first_content = next((line for line in text.splitlines() if line.strip()), "")
            if not first_content.startswith("## "):
                category_errors.append(f"{category}/{path.name}: must start with a `##` entry (no level-1 title chunk)")
            for line in text.splitlines():
                if line.startswith("#") and not line.startswith("## "):
                    category_errors.append(f"{category}/{path.name}: unsupported heading: {line[:40]}")
            parsed = parse_seed_entries(text)
            if not parsed:
                category_errors.append(f"{category}/{path.name}: no `##` entries")
                continue
            for entry in parsed:
                entry["file"] = path.name
                heading = entry["heading"]
                family = _role_family(heading)
                if not family:
                    category_errors.append(f"{category}/{path.name}: heading lacks role family separator: {heading}")
                else:
                    families.add(family)
                if heading in headings:
                    category_errors.append(f"{category}/{path.name}: duplicate heading: {heading}")
                headings.add(heading)
                for field in required_fields:
                    if not entry["fields"].get(field):
                        category_errors.append(f"{category}/{path.name}: missing field `{field}` in {heading}")
                question = entry["fields"].get("题目")
                if question:
                    if question in questions:
                        category_errors.append(f"{category}/{path.name}: duplicate question: {question}")
                    questions.add(question)
                length = len(entry["text"])
                report["max_entry_chars"] = max(report["max_entry_chars"], length)
                if length > MAX_ENTRY_CHARS:
                    category_errors.append(
                        f"{category}/{path.name}: entry {heading} is {length} chars (limit {MAX_ENTRY_CHARS})"
                    )
                entries.append(entry)

            chunks = chunk_document(
                text,
                chunk_size=settings.RAG_CHUNK_SIZE,
                overlap=settings.RAG_CHUNK_OVERLAP,
            )
            for chunk in chunks:
                chunk_length = len(chunk["text"])
                max_chunk_chars = max(max_chunk_chars, chunk_length)
                report["max_chunk_chars"] = max(report["max_chunk_chars"], chunk_length)
                if chunk_length > CONTEXT_SNIPPET_CHARS:
                    category_errors.append(
                        f"{category}/{path.name}: chunk {chunk['index']} is {chunk_length} chars; "
                        f"format_rag_context would cut it at {CONTEXT_SNIPPET_CHARS}"
                    )

        low, high = ENTRY_COUNT_RANGE
        if not low <= len(entries) <= high:
            category_errors.append(f"{category}: {len(entries)} entries, expected {low}-{high}")
        if len(families) < MIN_ROLE_FAMILIES:
            category_errors.append(f"{category}: {len(families)} role families, expected at least {MIN_ROLE_FAMILIES}")

        report["categories"][category] = {
            "files": len(files),
            "entries": len(entries),
            "role_families": len(families),
            "max_chunk_chars": max_chunk_chars,
        }
        report["errors"].extend(category_errors)

    report["ok"] = not report["errors"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import or validate bundled knowledge seed documents")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the structured role-family corpus without touching the database or embedding provider",
    )
    args = parser.parse_args(argv)

    if args.check:
        report = validate_seed_corpus()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2

    if not SEED_ROOT.exists():
        print(f"[ERROR] seed folder not found: {SEED_ROOT}")
        return 1

    overall_status = 0
    for folder_name, doc_type in SEED_MAPPINGS:
        folder = SEED_ROOT / folder_name
        if not folder.exists():
            print(f"[WARN] skip missing folder: {folder}")
            continue

        cmd = [
            sys.executable,
            str(IMPORT_SCRIPT),
            str(folder),
            "--doc-type",
            doc_type,
            "--recursive",
        ]
        print(f"[RUN] {' '.join(cmd)}")
        completed = subprocess.run(cmd, cwd=str(ROOT))
        if completed.returncode != 0:
            overall_status = completed.returncode

    return overall_status


if __name__ == "__main__":
    raise SystemExit(main())
