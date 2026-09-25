#!/usr/bin/env bash
# Restore verification (INF-001, BR-0025, strengthened by DEMO-011).
#
# "A successful backup is not evidence. A successful restore is."
#
# Restores the newest logical backup into a SEPARATE, THROWAWAY PostgreSQL
# SERVER — not a scratch database on the production one — then runs the
# platform's own deep integrity checks on the result and compares what came
# back against what the BACKUP'S OWN MANIFEST says it holds (WO-92).
#
# Why a separate server (DEMO-011 §5). The previous version created
# `lacteva_restore_check` inside the live instance. That is isolated by
# database, which is a real boundary, but it puts a restore drill and the
# production data under one postmaster: one bad `LACTEVA_DATABASE_URL`, one
# `DROP DATABASE` typed against the wrong session, one restore command that
# grows a `--force` flag, and the drill is indistinguishable from the
# accident. The whole point of a drill is that it CANNOT touch the thing it
# is rehearsing for. A throwaway container costs a few seconds and removes
# the question.
#
# Production is not read at all (WO-92): the comparison is the dump against
# itself, which is the only thing a restore can honestly be asked to prove.
#
#   ./verify-latest-backup.sh            # newest backup
#   BACKUP=/path/to/backup ./verify-latest-backup.sh
set -euo pipefail

# Container path (what the API sees) and host path (what this script globs).
# Conflating these is what broke the nightly script; see run-logical-backup.sh.
BACKUP_ROOT="${BACKUP_ROOT:-/backup/logical}"
BACKUP_HOST_DIR="${BACKUP_HOST_DIR:-${LACTEVA_BACKUP_DIR:-/var/lib/lacteva/backup}/logical}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production}"
NETWORK="${DRILL_NETWORK:-lacteva-production}"
DRILL_NAME="${DRILL_NAME:-lacteva-restore-drill}"
DRILL_PASSWORD="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')"
MAX_AGE_HOURS="${VERIFY_MAX_AGE_HOURS:-48}"

log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }
fail() { log "FAILED: $*"; exit 1; }

# The drill container and its data are removed whatever happens — including on
# failure, when the temptation to "leave it for a look" is exactly how a
# restored copy of live customer data outlives the drill (DEMO-011 §9).
cleanup() {
  log "removing the drill server and its data"
  docker rm -f "${DRILL_NAME}" >/dev/null 2>&1 || true
  docker volume rm "${DRILL_NAME}-data" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# --- 1. choose a backup ------------------------------------------------------
# Newest by MODIFICATION TIME, not by name. Sorting names put
# `predeploy-20260812T220548Z` ahead of `20260813T121038Z`, because 'p' sorts
# after '2' — so the drill verified a pre-deployment backup from the previous
# day and the scheduled one it was supposed to check was never looked at. Two
# naming schemes share this directory and always will; mtime does not care.
LATEST="${BACKUP:-$(find "${BACKUP_HOST_DIR}" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -rn | head -1 | cut -d' ' -f2-)}"
[ -n "${LATEST}" ] || fail "no backup found in ${BACKUP_HOST_DIR}"
STAMP="$(basename "${LATEST}")"
log "verifying ${STAMP}"

AGE_HOURS=$(( ( $(date +%s) - $(stat -c %Y "${LATEST}") ) / 3600 ))
if [ "${AGE_HOURS}" -gt "${MAX_AGE_HOURS}" ]; then
  fail "newest backup is ${AGE_HOURS}h old — the nightly job is not running"
fi
log "backup is ${AGE_HOURS}h old"

# --- 2. what does the BACKUP hold? ------------------------------------------
# WO-92. This step used to count rows in PRODUCTION, and step 6 compared the
# restored copy against that. Any row written after the dump was taken made
# the counts differ, so on a running system the drill could only pass in the
# dead of night — protected=NO every morning, and a REAL restore failure
# indistinguishable from the noise. The manifest now records, at dump time,
# the per-table row counts and the money it holds; the restored copy is
# compared with THAT (step 6), which is the only thing a restore can honestly
# be asked to prove. Production is no longer read at all.
MANIFEST_TABLES="$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(len(m["tables"]))' "${LATEST}/manifest.json" 2>/dev/null || echo 0)"
MANIFEST_MONEY="$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(sum(1 for v in m.get("money",{}).values() if v!="unavailable"))' "${LATEST}/manifest.json" 2>/dev/null || echo 0)"
[ "${MANIFEST_TABLES}" -gt 0 ] || fail "the manifest lists no tables"
log "manifest: ${MANIFEST_TABLES} tables, ${MANIFEST_MONEY} money figures recorded at dump time"
[ "${MANIFEST_MONEY}" -gt 0 ] || log "WARNING: this backup predates WO-92 and carries no money figures; rows only"

# --- 3. stand up an isolated server -----------------------------------------
log "starting an isolated PostgreSQL for the drill"
cleanup   # in case a previous run died before its trap
PG_IMAGE="$(${COMPOSE} config --images 2>/dev/null | grep -E '^postgres:' | head -1)"
PG_IMAGE="${PG_IMAGE:-postgres:16}"
docker volume create "${DRILL_NAME}-data" >/dev/null
docker run -d --name "${DRILL_NAME}" \
  --network "${NETWORK}" \
  -e POSTGRES_USER=drill \
  -e POSTGRES_PASSWORD="${DRILL_PASSWORD}" \
  -e POSTGRES_DB=lacteva \
  -v "${DRILL_NAME}-data:/var/lib/postgresql/data" \
  "${PG_IMAGE}" >/dev/null

for _ in $(seq 1 60); do
  docker exec "${DRILL_NAME}" pg_isready -U drill -d lacteva >/dev/null 2>&1 && break
  sleep 1
done
docker exec "${DRILL_NAME}" pg_isready -U drill -d lacteva >/dev/null 2>&1 \
  || fail "the drill server never became ready"
log "drill server ready (isolated; production untouched)"

DRILL_URL="postgresql+asyncpg://drill:${DRILL_PASSWORD}@${DRILL_NAME}:5432/lacteva"

# --- 4. migrate, then restore ------------------------------------------------
# A real recovery restores into a database at the BACKUP'S schema revision —
# not whatever head happens to be on the day of the drill. Those differ on
# every deploy day that carries a migration: the newest backup is then the
# pre-deployment safety dump, `upgrade head` put the drill one revision ahead
# of it, and the restore's schema-mismatch guard (correctly) refused — so the
# drill failed and paged, on a healthy system, for doing its job. The manifest
# records the revision the backup was taken at; the drill honours it.
REVISION="$(sed -n 's/.*"schema_revision"[[:space:]]*:[[:space:]]*"\([0-9a-f]*\)".*/\1/p' \
  "${LATEST}/manifest.json" | head -1)"
[ -n "${REVISION}" ] || fail "could not read schema_revision from ${LATEST}/manifest.json"
log "applying migrations to the drill server (to ${REVISION}, the backup's own revision)"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${DRILL_URL}" api \
  alembic upgrade "${REVISION}" >/dev/null || fail "migrations did not apply to the drill server"

log "restoring ${STAMP}"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${DRILL_URL}" api \
  python -m platform_core.core.backup.cli restore "${BACKUP_ROOT}/${STAMP}" \
  || fail "the restore did not complete"

# --- 5. is the restored BUSINESS correct? ------------------------------------
# The restore command runs integrity checks itself. `--deep` additionally
# rebuilds every projection from the restored event log and compares
# (BR-0015), which is the expensive half and why this is weekly.
log "deep integrity check (projection rebuild included)"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${DRILL_URL}" api \
  python -m platform_core.core.backup.cli integrity --deep \
  || fail "the restored database does not satisfy the platform's business rules"

# --- 6. does it hold what the backup holds? ---------------------------------
# Per table and per money figure, against the manifest's own dump-time
# numbers. `verify-restore` names every mismatch; `test_backup_restore.py`
# proves it goes red for a truncated table and for a changed amount.
log "comparing the restored copy with the backup's own manifest (rows and money)"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${DRILL_URL}" api \
  python -m platform_core.core.backup.cli verify-restore "${BACKUP_ROOT}/${STAMP}" \
  || fail "the restored database does not hold what the backup holds"
log "RESTORE VERIFIED: ${STAMP} restores to a correct platform"
