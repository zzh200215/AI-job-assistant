#!/usr/bin/env python3
"""
Backup MySQL database, uploaded files, and Chroma vector data.

Usage:
    python scripts/backup.py [--dry-run] [--keep N]

Backups are written to: <repo-root>/backups/YYYYMMDD_HHMMSS/
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from the backend package when running from repo root or backend dir.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402

logger = logging.getLogger("backup")


def _repo_root() -> Path:
    return _BACKEND_DIR.parent


def _chroma_dir() -> Path:
    return _BACKEND_DIR / "chroma_db"


def _upload_dir() -> Path:
    return Path(settings.UPLOAD_DIR).expanduser().resolve()


def _backup_base() -> Path:
    return _repo_root() / "backups"


def _run_command(cmd: list[str], dry_run: bool) -> None:
    logger.info("Would run: %s" if dry_run else "Running: %s", " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr}")
    if result.stdout:
        logger.info(result.stdout)


def _archive_directory(source: Path, archive_path: Path, dry_run: bool) -> None:
    if not source.exists():
        logger.warning("Source directory does not exist, skipping: %s", source)
        return
    cmd = [
        "tar",
        "-czf",
        str(archive_path),
        "-C",
        str(source.parent),
        str(source.name),
    ]
    _run_command(cmd, dry_run)


def _mysql_dump(output_file: Path, dry_run: bool) -> None:
    password = (settings.MYSQL_PASSWORD or "").strip()
    if not password and not dry_run:
        raise ValueError("MYSQL_PASSWORD is required for database backup")

    cmd = [
        "mysqldump",
        "--host",
        settings.MYSQL_HOST,
        "--port",
        str(settings.MYSQL_PORT),
        "--user",
        settings.MYSQL_USER,
        "--password=" + (password or "******"),
        "--single-transaction",
        "--routines",
        "--triggers",
        settings.MYSQL_DB,
    ]
    safe_cmd = [item if not item.startswith("--password=") else "--password=******" for item in cmd]

    logger.info("Would run: %s > %s" if dry_run else "Running: %s > %s", " ".join(safe_cmd), output_file)
    if dry_run:
        return

    with open(output_file, "w", encoding="utf-8") as f:
        result = subprocess.run(
            cmd,
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        if output_file.exists():
            output_file.unlink()
        raise RuntimeError(f"mysqldump failed ({result.returncode}): {result.stderr}")


def _cleanup_old_backups(keep_days: int, dry_run: bool) -> int:
    if keep_days <= 0:
        return 0
    base = _backup_base()
    if not base.exists():
        return 0

    removed = 0
    now = datetime.now(timezone.utc)
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        age_days = (now - mtime).days
        if age_days >= keep_days:
            logger.info("Removing old backup: %s (age=%d days)", entry, age_days)
            if not dry_run:
                shutil.rmtree(entry)
            removed += 1
    return removed


def _write_manifest(backup_dir: Path, files: list[str], dry_run: bool) -> None:
    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app_env": settings.APP_ENV,
        "files": files,
    }
    manifest_path = backup_dir / "manifest.json"
    logger.info("Would write manifest: %s", manifest_path)
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup database, uploads and Chroma data")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际写入文件")
    parser.add_argument("--keep", type=int, default=0, help="保留最近 N 天的备份，0 表示不清理")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    keep_days = args.keep or settings.BACKUP_KEEP_DAYS

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = _backup_base() / timestamp
    files: list[str] = []

    try:
        if not args.dry_run:
            backup_dir.mkdir(parents=True, exist_ok=True)

        # MySQL
        sql_file = backup_dir / f"{settings.MYSQL_DB}.sql"
        _mysql_dump(sql_file, args.dry_run)
        files.append(str(sql_file.name))

        # Uploads
        uploads_archive = backup_dir / "uploads.tar.gz"
        _archive_directory(_upload_dir(), uploads_archive, args.dry_run)
        files.append(str(uploads_archive.name))

        # Chroma
        chroma_archive = backup_dir / "chroma.tar.gz"
        _archive_directory(_chroma_dir(), chroma_archive, args.dry_run)
        files.append(str(chroma_archive.name))

        _write_manifest(backup_dir, files, args.dry_run)

        removed = _cleanup_old_backups(keep_days, args.dry_run)
        logger.info(
            "Backup %s completed: %s (%d old backups removed)",
            "dry-run" if args.dry_run else "",
            backup_dir,
            removed,
        )
        return 0
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
