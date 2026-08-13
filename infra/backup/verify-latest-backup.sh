#!/usr/bin/env bash
# Restore verification (INF-001, BR-0025, strengthened by DEMO-011).
#
# "A successful backup is not evidence. A successful restore is."
#
# Restores the newest logical backup into a SEPARATE, THROWAWAY PostgreSQL
# SERVER — not a scratch database on the production one — then runs the
# platform's own deep integrity checks on the result and compares what came
# back against what production actually holds.
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
# Production is read ONLY, and only to count rows for comparison.
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

# --- 2. what does production hold? ------------------------------------------
# Read-only, and taken BEFORE the restore so the comparison cannot be
# influenced by it. The tables DEMO-011 §5 names, by their real names — `audit_record`, not
# `audit_log`, which is what the first draft guessed and what made the drill
# fail on its own comparison query rather than on anything about the backup.
TABLES="organization user_account role user_role customer supplier \
collection_center milk_collection_transaction milk_delivery settlement \
payment receipt customer_invoice customer_payment customer_receipt \
audit_record"

# PER TABLE, not a single total. Two tables wrong by +1 and -1 sum to the
# right answer, and that is exactly the shape a partial restore takes.
counts_sql() {
  local first=1
  for tbl in ${TABLES}; do
    [ ${first} -eq 1 ] && first=0 || printf " UNION ALL "
    printf "SELECT '%s' AS t, count(*) AS n FROM %s" "${tbl}" "${tbl}"
  done
  printf " ORDER BY 1"
}

log "counting production rows, per table (read only)"
PROD_COUNTS="$(${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -tA -F'=' -c "$(counts_sql)" 2>/dev/null | tr -d '\r')"
[ -n "${PROD_COUNTS}" ] || fail "could not read production row counts"

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
# A real recovery restores into a MIGRATED database, so the drill does too.
log "applying migrations to the drill server"
${COMPOSE} run --rm --no-deps -T -e "LACTEVA_DATABASE_URL=${DRILL_URL}" api \
  alembic upgrade head >/dev/null || fail "migrations did not apply to the drill server"

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

# --- 6. does it hold what production holds? ----------------------------------
log "comparing restored row counts against production, per table"
DRILL_COUNTS="$(docker exec "${DRILL_NAME}" psql -U drill -d lacteva \
  -tA -F'=' -c "$(counts_sql)" | tr -d '\r')"

MISMATCH=0
while IFS='=' read -r tbl n; do
  [ -n "${tbl}" ] || continue
  got="$(printf '%s\n' "${DRILL_COUNTS}" | awk -F= -v t="${tbl}" '$1==t {print $2}')"
  if [ "${n}" = "${got}" ]; then
    printf '    %-32s %8s  ok\n' "${tbl}" "${n}"
  else
    printf '    %-32s %8s  RESTORED %s  MISMATCH\n' "${tbl}" "${n}" "${got:-missing}"
    MISMATCH=1
  fi
done <<< "${PROD_COUNTS}"

[ "${MISMATCH}" -eq 0 ] \
  || fail "the restored database does not hold what production holds"

# --- 7. does it hold the same MONEY? -----------------------------------------
# Row counts prove the rows arrived. They say nothing about whether the values
# in them survived, and a backup that restores the right number of wrong
# amounts is the worst possible outcome for a platform that settles payments.
# Sums are exact `numeric`, compared as text, so no float ever enters this.
MONEY_SQL="SELECT 'settlement.net'      AS k, coalesce(sum(net_amount),0)::text FROM settlement
     UNION ALL SELECT 'settlement.gross',      coalesce(sum(gross_amount),0)::text FROM settlement
     UNION ALL SELECT 'payment.amount',        coalesce(sum(amount),0)::text FROM payment
     UNION ALL SELECT 'receipt.net',           coalesce(sum(net_amount),0)::text FROM receipt
     UNION ALL SELECT 'delivery.amount',       coalesce(sum(amount),0)::text FROM milk_delivery
     UNION ALL SELECT 'invoice.total',         coalesce(sum(total),0)::text FROM customer_invoice
     UNION ALL SELECT 'invoice.amount_due',    coalesce(sum(amount_due),0)::text FROM customer_invoice
     UNION ALL SELECT 'customer_payment.amt',  coalesce(sum(amount),0)::text FROM customer_payment
     UNION ALL SELECT 'customer_receipt.amt',  coalesce(sum(amount),0)::text FROM customer_receipt
     UNION ALL SELECT 'collection.gross',      coalesce(sum(gross_amount),0)::text FROM milk_collection_transaction
     ORDER BY 1"

log "comparing money, not just rows"
PROD_MONEY="$(${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -tA -F'=' -c "${MONEY_SQL}" 2>/dev/null | tr -d '\r')"
DRILL_MONEY="$(docker exec "${DRILL_NAME}" psql -U drill -d lacteva -tA -F'=' -c "${MONEY_SQL}" | tr -d '\r')"

while IFS='=' read -r k v; do
  [ -n "${k}" ] || continue
  got="$(printf '%s\n' "${DRILL_MONEY}" | awk -F= -v t="${k}" '$1==t {print $2}')"
  if [ "${v}" = "${got}" ]; then
    printf '    %-24s %16s  ok\n' "${k}" "${v}"
  else
    printf '    %-24s %16s  RESTORED %s  MISMATCH\n' "${k}" "${v}" "${got:-missing}"
    MISMATCH=1
  fi
done <<< "${PROD_MONEY}"

[ "${MISMATCH}" -eq 0 ] \
  || fail "the restored database does not hold the same money as production"

log "RESTORE VERIFIED: ${STAMP} restores to a correct platform"
