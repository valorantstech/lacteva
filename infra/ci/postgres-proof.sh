#!/usr/bin/env bash
# PostgreSQL proof (CI-001).
#
# Converts every PostgreSQL-dependent guarantee from "documented" to "proven",
# by executing it against a real engine:
#
#   1. migrations apply to an EMPTY database
#   2. RLS policies exist, are FORCED, and COVER every tenant-owned table
#   3. the PostgreSQL-only test suite passes (and did not silently skip)
#   4. a real dairy is seeded through the platform's own API
#   5. a logical backup is taken and verified
#   6. a SECOND, fresh database is migrated
#   7. the backup is restored into it
#   8. the restored data passes deep business-integrity verification
#   9. source and restored databases are compared fact by fact
#
# CI runs this file. `docker compose -f docker-compose.proof.yml run proof`
# runs the same file. There is deliberately one code path, so "works in CI"
# and "works on my machine" cannot drift apart.
#
# Any failure fails the build. A skipped test fails the build too — a
# silently skipped proof is worse than no proof, because it is green.
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-lacteva}"
PGPASSWORD="${PGPASSWORD:-lacteva}"
export PGPASSWORD

SOURCE_DB="${SOURCE_DB:-lacteva_proof}"
RESTORE_DB="${RESTORE_DB:-lacteva_restore}"
WORKDIR="$(mktemp -d)"
BACKUP_DIR="${WORKDIR}/backup"

# Run from the service root regardless of where the script was invoked.
cd "$(dirname "${BASH_SOURCE[0]}")/../../services/platform-core"

RUN="${RUN:-uv run}"

url_for() { echo "postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/$1"; }
psql_do() { psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "$1" -tAc "$2"; }

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mPROOF FAILED: %s\033[0m\n' "$*" >&2; exit 1; }

trap 'rm -rf "${WORKDIR}"' EXIT

# The seeder and CLI must not start background loops: their sessions would
# interleave with the work being measured. Consumers are driven explicitly.
export LACTEVA_ENV=staging
export LACTEVA_EVENT_BUS=memory
export LACTEVA_OUTBOX_MODE=inline
export LACTEVA_CONSUMERS_ENABLED=false
export LACTEVA_RATE_LIMIT_BACKEND=memory
export LACTEVA_MINIO_SECRET_KEY=proof-not-a-real-secret

step "0/9  waiting for PostgreSQL at ${PGHOST}:${PGPORT}"
for _ in $(seq 1 60); do
  pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" >/dev/null 2>&1 && break
  sleep 1
done
pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" >/dev/null 2>&1 \
  || fail "PostgreSQL never became ready"
psql_do postgres "SELECT version()" | head -1

step "1/9  migrations apply to an EMPTY database (${SOURCE_DB})"
psql_do postgres "DROP DATABASE IF EXISTS ${SOURCE_DB}" >/dev/null
psql_do postgres "CREATE DATABASE ${SOURCE_DB}" >/dev/null
LACTEVA_DATABASE_URL="$(url_for "${SOURCE_DB}")" ${RUN} alembic upgrade head \
  || fail "migrations did not apply to an empty database"
TABLES="$(psql_do "${SOURCE_DB}" \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
echo "    ${TABLES} tables created"
[ "${TABLES}" -gt 40 ] || fail "only ${TABLES} tables after migration — expected the full schema"

step "2/9  row-level security is enabled AND forced on every tenant-owned table"
# `relrowsecurity` alone is not enough: without FORCE the table owner — which
# is who the application connects as — bypasses its own policies.
UNFORCED="$(psql_do "${SOURCE_DB}" \
  "SELECT count(*) FROM pg_class WHERE relrowsecurity AND NOT relforcerowsecurity")"
[ "${UNFORCED}" = "0" ] || fail "${UNFORCED} table(s) have RLS enabled but NOT forced"
PROTECTED="$(psql_do "${SOURCE_DB}" \
  "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity")"
echo "    ${PROTECTED} tables protected and forced"
[ "${PROTECTED}" -gt 30 ] || fail "only ${PROTECTED} protected tables — policies are missing"
POLICIES="$(psql_do "${SOURCE_DB}" "SELECT count(*) FROM pg_policies WHERE schemaname='public'")"
echo "    ${POLICIES} policies present"

# SEC-002: coverage, not just presence. Every table that carries a tenant_id
# must have a policy, and `organization` — which IS the tenant and therefore
# has no tenant_id — must have one too. Counting policies would pass while the
# money and PII tables sat unprotected, which is exactly what happened.
UNCOVERED="$(psql_do "${SOURCE_DB}" "
  SELECT count(*) FROM information_schema.columns c
  WHERE c.table_schema='public' AND c.column_name='tenant_id'
    AND NOT EXISTS (SELECT 1 FROM pg_policies p
                    WHERE p.schemaname='public' AND p.tablename=c.table_name)")"
[ "${UNCOVERED}" = "0" ] || fail "${UNCOVERED} table(s) carry tenant_id but have NO policy"
ORG_POLICY="$(psql_do "${SOURCE_DB}" \
  "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='organization'")"
[ "${ORG_POLICY}" = "1" ] || fail "organization has no RLS policy — a tenant can enumerate tenants"
echo "    every tenant_id table covered; organization isolated by identity"

step "3/9  PostgreSQL-only test suite (RLS enforcement)"
RLS_LOG="${WORKDIR}/rls.log"
LACTEVA_TEST_POSTGRES_URL="$(url_for "${SOURCE_DB}")" \
  ${RUN} pytest tests/test_rls_postgres.py -v --no-header -rs 2>&1 | tee "${RLS_LOG}" \
  || fail "RLS enforcement tests failed"
# A skipped security proof is worse than none: it is green.
grep -qE "[0-9]+ skipped" "${RLS_LOG}" \
  && fail "RLS tests SKIPPED — PostgreSQL was not reachable from pytest"
grep -qE "[0-9]+ passed" "${RLS_LOG}" || fail "no RLS tests actually ran"

step "4/9  seeding a real dairy through the platform's own API"
LACTEVA_DATABASE_URL="$(url_for "${SOURCE_DB}")" \
  ${RUN} python ../../infra/ci/seed_proof_data.py > "${WORKDIR}/seed.json" \
  || fail "seeding failed"
cat "${WORKDIR}/seed.json"

step "5/9  logical backup + checksum verification"
LACTEVA_DATABASE_URL="$(url_for "${SOURCE_DB}")" \
  ${RUN} python -m platform_core.core.backup.cli backup "${BACKUP_DIR}" \
  || fail "backup failed"
LACTEVA_DATABASE_URL="$(url_for "${SOURCE_DB}")" \
  ${RUN} python -m platform_core.core.backup.cli verify "${BACKUP_DIR}" \
  || fail "the backup did not verify against its own checksums"

step "6/9  a SECOND, fresh database (${RESTORE_DB})"
psql_do postgres "DROP DATABASE IF EXISTS ${RESTORE_DB}" >/dev/null
psql_do postgres "CREATE DATABASE ${RESTORE_DB}" >/dev/null
LACTEVA_DATABASE_URL="$(url_for "${RESTORE_DB}")" ${RUN} alembic upgrade head \
  || fail "migrations did not apply to the restore target"

step "7/9  restoring into the fresh database"
LACTEVA_DATABASE_URL="$(url_for "${RESTORE_DB}")" \
  ${RUN} python -m platform_core.core.backup.cli restore "${BACKUP_DIR}" \
  || fail "restore failed, or the restored data violated a business rule"

step "8/9  deep integrity of the RESTORED database"
# Rebuilds every projection from the restored event log and compares (BR-0015),
# on top of the settlement/payment/receipt invariants.
LACTEVA_DATABASE_URL="$(url_for "${RESTORE_DB}")" \
  ${RUN} python -m platform_core.core.backup.cli integrity --deep \
  || fail "the restored database violates the platform's own business rules"

step "9/9  comparing source and restored, fact by fact"
mismatch=0
for check in \
  "settlement:SELECT settlement_number || ':' || net_amount FROM settlement ORDER BY 1" \
  "payment:SELECT payment_number || ':' || amount || ':' || status FROM payment ORDER BY 1" \
  "receipt:SELECT receipt_number || ':' || net_amount FROM receipt ORDER BY 1" \
  "outbox:SELECT count(*)::text FROM event_outbox" \
  "audit:SELECT count(*)::text FROM audit_record" \
  "cursors:SELECT consumer_name FROM consumer_cursor ORDER BY 1" \
; do
  name="${check%%:*}"; sql="${check#*:}"
  a="$(psql_do "${SOURCE_DB}" "${sql}")"
  b="$(psql_do "${RESTORE_DB}" "${sql}")"
  if [ "${a}" = "${b}" ]; then
    printf '    %-10s match  %s\n' "${name}" "$(echo "${a}" | tr '\n' ' ' | cut -c1-60)"
  else
    printf '    %-10s MISMATCH\n      source:   %s\n      restored: %s\n' "${name}" "${a}" "${b}"
    mismatch=1
  fi
done
[ "${mismatch}" = "0" ] || fail "the restored database differs from its source"

cat <<'DONE'

╭──────────────────────────────────────────────────────────────╮
│  POSTGRESQL PROOF PASSED                                     │
│                                                              │
│  migrations from empty ....... proven                        │
│  RLS enabled + forced ........ proven                        │
│  RLS enforcement tests ....... proven (not skipped)          │
│  logical backup + checksums .. proven                        │
│  restore into a fresh DB ..... proven                        │
│  business integrity (deep) ... proven                        │
│  source vs restored .......... identical                     │
╰──────────────────────────────────────────────────────────────╯
DONE
