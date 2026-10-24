#!/usr/bin/env python
"""Measure real resume file extraction (P2 gap: eval starts from raw_text)."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.history import Resume  # noqa: E402
from app.utils.file_parser import parse_resume  # noqa: E402

REPORT = ROOT / "reports" / "file_extraction_measure.json"


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def summarize(details: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for item in details:
        bucket = by_type.setdefault(
            item["file_type"],
            {"files": 0, "ok": 0, "failed": 0, "exact": 0, "normalized": 0, "chars": [], "errors": []},
        )
        bucket["files"] += 1
        if item["ok"]:
            bucket["ok"] += 1
            bucket["chars"].append(item["chars"])
            bucket["exact"] += int(item["exact"])
            bucket["normalized"] += int(item["normalized"])
        else:
            bucket["failed"] += 1
            bucket["errors"].append(item["error"])
    for bucket in by_type.values():
        chars = bucket.pop("chars")
        bucket["chars_median"] = int(statistics.median(chars)) if chars else None
        bucket["chars_min"] = min(chars) if chars else None
        bucket["chars_max"] = max(chars) if chars else None
    return by_type


def measure() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = [
            row for row in db.query(Resume).filter(Resume.file_path.isnot(None)).all() if (row.file_path or "").strip()
        ]
    finally:
        db.close()

    details: list[dict[str, Any]] = []
    for row in rows:
        path = pathlib.Path(row.file_path or "")
        if not path.is_absolute():
            path = ROOT / path
        file_type = str(row.file_type or path.suffix.lstrip(".")).lower()
        item = {
            "resume_id": row.id,
            "file": path.name,
            "file_type": file_type,
            "ok": False,
            "chars": 0,
            "exact": False,
            "normalized": False,
            "ratio": None,
            "error": "",
        }
        if not path.exists():
            item["error"] = "FileNotFoundError"
            details.append(item)
            continue
        try:
            text = parse_resume(str(path), file_type)
        except Exception as exc:  # 量的是"这一层对真文件的行为"，异常也是读数
            item["error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
            details.append(item)
            continue

        stored = row.raw_text or ""
        item.update(
            {
                "ok": True,
                "chars": len(text),
                "exact": text.strip() == stored.strip(),
                "normalized": normalize(text) == normalize(stored),
                "ratio": round(len(normalize(text)) / len(normalize(stored)), 3) if normalize(stored) else None,
            }
        )
        details.append(item)
    return details, summarize(details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure real resume file extraction")
    parser.add_argument("--output", default=str(REPORT))
    args = parser.parse_args(argv)

    details, summary = measure()
    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = [item for item in details if not item["ok"]]
    if failures:
        print(f"failures {len(failures)}:")
        for item in failures:
            print(f"  {item['file_type']} {item['file']}: {item['error']}")
    print(f"report {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
