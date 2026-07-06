#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Incrementally import knowledge documents from a local folder."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.knowledge import KnowledgeDocument  # noqa: E402
from app.schemas.knowledge import DOC_TYPE_CHOICES  # noqa: E402
from app.services import knowledge_service  # noqa: E402

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".doc"}


def iter_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path for path in folder.glob(pattern)
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    )


def default_title(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def exists(db, *, title: str, file_name: str, doc_type: str) -> bool:
    return db.query(KnowledgeDocument).filter(
        KnowledgeDocument.title == title,
        KnowledgeDocument.file_name == file_name,
        KnowledgeDocument.doc_type == doc_type,
        KnowledgeDocument.status == "ready",
    ).first() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Incrementally import knowledge files")
    parser.add_argument("folder", help="Folder containing documents to ingest")
    parser.add_argument("--doc-type", required=True, choices=DOC_TYPE_CHOICES)
    parser.add_argument("--user-id", type=int, default=None, help="Owner user_id for imported documents")
    parser.add_argument("--recursive", action="store_true", help="Scan subfolders recursively")
    parser.add_argument("--no-skip-existing", action="store_true", help="Import duplicates instead of skipping them")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"[ERROR] folder not found: {folder}")
        return 1

    files = iter_files(folder, args.recursive)
    if not files:
        print(f"[WARN] no supported files found in {folder}")
        return 0

    db = SessionLocal()
    imported = 0
    skipped = 0
    failed = 0
    try:
        for path in files:
            title = default_title(path)
            if not args.no_skip_existing and exists(db, title=title, file_name=path.name, doc_type=args.doc_type):
                skipped += 1
                print(f"[SKIP] {path.name}")
                continue

            try:
                payload = path.read_bytes()
                doc = knowledge_service.save_and_process(
                    db,
                    payload,
                    path.name,
                    title,
                    args.doc_type,
                    user_id=args.user_id,
                )
                if doc.status == "ready":
                    imported += 1
                    print(f"[OK]   {path.name} -> doc_id={doc.id} chunks={doc.chunk_count}")
                else:
                    failed += 1
                    print(f"[FAIL] {path.name} -> doc_id={doc.id} error={doc.error_msg}")
            except Exception as exc:
                failed += 1
                print(f"[FAIL] {path.name} -> {exc}")
    finally:
        db.close()

    print(
        f"[DONE] imported={imported} skipped={skipped} failed={failed} "
        f"doc_type={args.doc_type} folder={folder}"
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
