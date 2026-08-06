#!/usr/bin/env bash
# Restore verification (INF-001, BR-0025).
#
# "A successful backup is not evidence. A successful restore is."
#
# Restores the newest logical backup into a THROWAWAY database and runs the
# platform's own deep integrity checks on the result — settlement totals,
# payment allocations, one receipt per completed payment, consumer cursors
# within the log, and a full projection rebuild compared against what was
# restored. It fails if the restored BUSINESS is wrong, not merely if rows
# failed to load.
#
# Runs against a scratch database on the same server, never the live one.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/backup/logical}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production}"
SCRATCH_DB="${VERIFY_DB:-lacteva_restore_check}"

log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }
cleanup() {
  log "dropping ${SCRATCH_DB}"
  ${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER}" -d postgres \
    -c "DROP DATABASE IF EXISTS ${SCRATCH_DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

LATEST="$(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)"
[ -n "${LATEST}" ] || { log "FAILED: no backup found in ${BACKUP_ROOT}"; exit 1; }
log "verifying ${LATEST}"

AGE_HOURS=$(( ( $(date +%s) - $(stat -c %Y "${LATEST}") ) / 3600 ))
if [ "${AGE_HOURS}" -gt 48 ]; then
  log "FAILED: newest backup is ${AGE_HOURS}h old — the nightly job is not running"
  exit 1
fi

log "creating scratch database ${SCRATCH_DB}"
${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${SCRATCH_DB}" >/dev/null
${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER}" -d postgres \
  -c "CREATE DATABASE ${SCRATCH_DB}" >/dev/null

SCRATCH_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${SCRATCH_DB}"

# The restore target must be a MIGRATED database, not an empty one — that is
# how a real recovery works, and restoring into an unmigrated database would
# test a path nobody uses.
log "applying migrations to the scratch database"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${SCRATCH_URL}" api alembic upgrade head

log "restoring"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${SCRATCH_URL}" api \
  python -m platform_core.core.backup.cli restore "${LATEST}"

# The restore command already runs integrity checks and exits non-zero when
# the business is wrong. Running --deep separately also rebuilds every
# projection from the restored event log and compares (BR-0015), which is the
# expensive half and the reason this is weekly rather than nightly.
log "deep integrity check (projection rebuild included)"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${SCRATCH_URL}" api \
  python -m platform_core.core.backup.cli integrity --deep

log "RESTORE VERIFIED: ${LATEST} restores to a correct platform"
