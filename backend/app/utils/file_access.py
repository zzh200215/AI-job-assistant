"""Helpers for resolving files stored under the upload directory."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings


def uploads_root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


def resolve_upload_path(relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("empty upload path")

    normalized = str(relative_path).replace("\\", "/").lstrip("/")
    upload_dir_name = uploads_root().name
    prefix = f"{upload_dir_name}/"
    if normalized == upload_dir_name:
        normalized = ""
    elif normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]

    target = (uploads_root() / normalized).resolve()
    if os.path.commonpath([str(uploads_root()), str(target)]) != str(uploads_root()):
        raise ValueError("upload path escapes upload root")
    return target
