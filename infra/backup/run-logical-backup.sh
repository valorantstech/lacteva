#!/usr/bin/env bash
# Nightly logical backup with retention (INF-001).
#
# Wraps the platform's own backup CLI so the systemd timer has one thing to
# call. Three responsibilities, in this order:
#
#   1. take the backup      — through the running API container
#   2. VERIFY it            — re-checksum on disk; an unverified backup is a hope
#   3. prune old ones       — but only AFTER a successful, verified new one
#
# The ordering in 3 is the point. Pruning before the new backup succeeds means
# a failing backup job quietly deletes its way through the retention window,
# and the day you need a restore there is nothing left. Deleting last means
# the worst case is too many backups, which costs disk and nothing else.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/backup/logical}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-30}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_ROOT}/${STAMP}"

log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }

log "starting logical backup -> ${TARGET}"
mkdir -p "${BACKUP_ROOT}"

if ! ${COMPOSE} exec -T api python -m platform_core.core.backup.cli backup "${TARGET}"; then
  log "FAILED: backup did not complete. Nothing pruned."
  exit 1
fi

# Verify separately rather than trusting the write path. The engine checks its
# own checksums as it writes; this re-reads them from disk, which is a
# different question and the one that matters after a bad sector.
if ! ${COMPOSE} exec -T api python -m platform_core.core.backup.cli verify "${TARGET}"; then
  log "FAILED: backup does not verify against its own checksums. Nothing pruned."
  exit 1
fi
log "backup verified"

# BKP-003: get it OFF this volume before doing anything else. A verified backup
# that only exists beside the database it protects is not a backup — losing the
# volume loses both. Replication happens before pruning for the same reason
# pruning happens after the backup: the worst case must be too many copies.
if ! ${COMPOSE} exec -T api python -m platform_core.core.backup.cli replicate "${TARGET}"; then
  log "FAILED: backup did not reach off-site storage. Nothing pruned."
  exit 1
fi
log "backup replicated off-site"

# Off-site retention. `--delete` is required because the CLI defaults to a dry
# run; the platform's own rules (never below 1, never the newest, nothing when
# there are fewer than `keep`) are enforced inside it, not here.
${COMPOSE} exec -T api python -m platform_core.core.backup.cli offsite-prune --delete \
  || log "WARNING: off-site retention failed. Copies retained; investigate."

# Only now.
log "pruning backups older than ${RETAIN_DAYS} days"
DELETED=0
while IFS= read -r -d '' old; do
  log "  removing $(basename "${old}")"
  rm -rf "${old}"
  DELETED=$((DELETED + 1))
done < <(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETAIN_DAYS}" -print0)

REMAINING="$(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d | wc -l)"
if [ "${REMAINING}" -lt 1 ]; then
  log "FAILED: retention removed everything. This should be impossible."
  exit 1
fi

USAGE="$(df -h "${BACKUP_ROOT}" | awk 'NR==2 {print $5" used, "$4" free"}')"
log "done: ${REMAINING} backup(s) retained, ${DELETED} pruned. Volume: ${USAGE}"
