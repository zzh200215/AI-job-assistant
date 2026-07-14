#!/usr/bin/env python
"""Import the bundled knowledge seed documents."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT = ROOT.parent / "docs" / "knowledge-seeds"
IMPORT_SCRIPT = ROOT / "scripts" / "import_knowledge.py"

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


def main() -> int:
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
