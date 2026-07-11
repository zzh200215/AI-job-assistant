#!/usr/bin/env bash
# Restore MySQL, uploads, and Chroma data from a backup directory.
#
# Usage:
#   ./scripts/restore.sh /path/to/backups/20260711_120000
#   ./scripts/restore.sh /path/to/backups/20260711_120000 --dry-run
#
# The script will prompt for "YES" before overwriting any data unless --dry-run
# is provided.

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup-directory> [--dry-run]" >&2
    exit 1
fi

BACKUP_DIR="$1"
DRY_RUN=false
if [ "${2:-}" = "--dry-run" ]; then
    DRY_RUN=true
fi

if [ ! -d "${BACKUP_DIR}" ]; then
    echo "Error: backup directory does not exist: ${BACKUP_DIR}" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"

SQL_FILE="${BACKUP_DIR}/$(basename "${BACKUP_DIR}").sql"
if [ ! -f "${SQL_FILE}" ]; then
    # Fallback to the database name used by the application.
    SQL_FILE="${BACKUP_DIR}/llmXM.sql"
fi
UPLOADS_ARCHIVE="${BACKUP_DIR}/uploads.tar.gz"
CHROMA_ARCHIVE="${BACKUP_DIR}/chroma.tar.gz"
MANIFEST_FILE="${BACKUP_DIR}/manifest.json"

UPLOADS_DIR="${BACKEND_DIR}/uploads"
CHROMA_DIR="${BACKEND_DIR}/chroma_db"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_DB="${MYSQL_DB:-llmXM}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"

if [ -z "${MYSQL_PASSWORD}" ]; then
    echo "Error: MYSQL_PASSWORD environment variable is required." >&2
    exit 1
fi

echo "Backup to restore: ${BACKUP_DIR}"
if [ -f "${MANIFEST_FILE}" ]; then
    echo "Manifest:"
    cat "${MANIFEST_FILE}"
fi

echo ""
echo "This will OVERWRITE the current database, uploads, and Chroma data."
if [ "$DRY_RUN" = true ]; then
    echo "Running in DRY-RUN mode. No data will be modified."
else
    read -r -p 'Type YES to continue: ' CONFIRM
    if [ "${CONFIRM}" != "YES" ]; then
        echo "Restore cancelled."
        exit 1
    fi
fi

run_or_echo() {
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] Would run: $*"
    else
        echo "Running: $*"
        "$@"
    fi
}

# Restore database
if [ -f "${SQL_FILE}" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] Would run: mysql --host=${MYSQL_HOST} --port=${MYSQL_PORT} --user=${MYSQL_USER} ${MYSQL_DB} < ${SQL_FILE}"
    else
        echo "Running: mysql --host=${MYSQL_HOST} --port=${MYSQL_PORT} --user=${MYSQL_USER} ${MYSQL_DB} < ${SQL_FILE}"
        MYSQL_PWD="${MYSQL_PASSWORD}" mysql --host="${MYSQL_HOST}" --port="${MYSQL_PORT}" --user="${MYSQL_USER}" "${MYSQL_DB}" < "${SQL_FILE}"
    fi
else
    echo "Warning: SQL dump not found at ${SQL_FILE}, skipping database restore." >&2
fi

# Restore uploads
if [ -f "${UPLOADS_ARCHIVE}" ]; then
    run_or_echo mkdir -p "${UPLOADS_DIR}"
    run_or_echo tar -xzf "${UPLOADS_ARCHIVE}" -C "${UPLOADS_DIR%/*}"
else
    echo "Warning: uploads archive not found at ${UPLOADS_ARCHIVE}, skipping." >&2
fi

# Restore Chroma
if [ -f "${CHROMA_ARCHIVE}" ]; then
    run_or_echo mkdir -p "${CHROMA_DIR}"
    run_or_echo tar -xzf "${CHROMA_ARCHIVE}" -C "${CHROMA_DIR%/*}"
else
    echo "Warning: Chroma archive not found at ${CHROMA_ARCHIVE}, skipping." >&2
fi

if [ "$DRY_RUN" = true ]; then
    echo "Dry-run restore completed. No changes were made."
else
    echo "Restore completed from ${BACKUP_DIR}."
fi
