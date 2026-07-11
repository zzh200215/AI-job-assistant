#!/usr/bin/env bash
# Backup wrapper for cron or manual execution.
# Usage:
#   ./scripts/backup.sh
#   ./scripts/backup.sh --dry-run
#
# The script changes to the repository root before invoking the Python backup
# script so that relative paths (uploads/, chroma_db/, backups/) resolve
# correctly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/backups"

mkdir -p "${BACKUP_DIR}"

if ! command -v mysqldump >/dev/null 2>&1; then
    echo "Error: mysqldump is required but not installed." >&2
    exit 1
fi

exec >> "${BACKUP_DIR}/backup.log" 2>&1
echo "[$(date -Iseconds)] Starting backup"

if python3 "${BACKEND_DIR}/scripts/backup.py" "$@"; then
    echo "[$(date -Iseconds)] Backup completed successfully"
else
    echo "[$(date -Iseconds)] Backup failed"
    exit 1
fi
