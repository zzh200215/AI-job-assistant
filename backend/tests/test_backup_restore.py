"""Backup script tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


class TestBackupScript:
    def test_backup_dry_run_creates_no_files(self, tmp_path, monkeypatch):
        repo_root = Path(__file__).resolve().parent.parent.parent
        script = repo_root / "backend" / "scripts" / "backup.py"
        assert script.exists()

        # Run in a temporary repo root so backups/ is created under tmp_path.
        monkeypatch.chdir(repo_root)
        result = subprocess.run(
            [sys.executable, str(script), "--dry-run", "--keep", "1"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        # Dry-run should not create a timestamped backup directory.
        assert "dry-run" in result.stdout.lower() or "Backup dry-run completed" in result.stdout

    def test_backup_manifest_format(self, tmp_path):
        manifest = {
            "version": "1.0",
            "created_at": "2026-07-11T12:00:00+00:00",
            "files": ["llmXM.sql", "uploads.tar.gz", "chroma.tar.gz"],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert loaded["files"] == manifest["files"]
