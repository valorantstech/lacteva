#!/usr/bin/env bash
# PostgreSQL physical backup (BAK-001).
#
# The production first line: a base backup plus continuous WAL archiving,
# which together give point-in-time recovery. The platform's own logical
# backup (`python -m platform_core.core.backup.cli backup`) is the verifiable
# second line — see BACKUP.md for why both exist.
#
# This script does NOT verify the backup. Verification requires restoring it,
# which is what pg-restore-test.sh does, and a backup nobody has restored is
# not evidence of anything.
set -euo pipefail

: "${PGHOST:?set PGHOST}"
: "${PGUSER:?set PGUSER}"
: "${BACKUP_ROOT:?set BACKUP_ROOT (e.g. /var/backups/lacteva)}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_ROOT}/base/${STAMP}"
mkdir -p "${TARGET}"

echo "==> base backup -> ${TARGET}"
# -X stream: ship the WAL generated DURING the backup with it, so the base is
# self-consistent without depending on the archive having caught up.
# -C -c fast: checkpoint immediately rather than waiting, so the window in
# which the backup lags the database is as small as possible.
pg_basebackup \
  --pgdata="${TARGET}" \
  --format=tar --gzip --compress=6 \
  --wal-method=stream \
  --checkpoint=fast \
  --progress --verbose

echo "==> recording the manifest checksum"
# pg_basebackup writes backup_manifest with per-file checksums; keep a digest
# of it so tampering with both file and manifest is detectable.
sha256sum "${TARGET}/backup_manifest" > "${TARGET}/backup_manifest.sha256" 2>/dev/null || true

echo "==> pruning base backups older than ${RETENTION_DAYS:-35} days"
find "${BACKUP_ROOT}/base" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS:-35}" \
  -exec rm -rf {} + 2>/dev/null || true

echo "==> done: ${TARGET}"
echo "REMINDER: this backup is unverified until pg-restore-test.sh has restored it."
