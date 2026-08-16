#!/usr/bin/env bash
# PostgreSQL proof (CI-001).
#
# Converts every PostgreSQL-dependent guarantee from "documented" to "proven",
# by executing it against a real engine:
#
#   1. migrations apply to an EMPTY database
#   2. RLS policies exist, are FORCED, and COVER every tenant-owned table
#   3. the PostgreSQL-only suites pass (RLS + exact aggregation; no skips)
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

# VER-001. The role the APPLICATION connects as, which is not the role that
# owns the schema and is emphatically not a superuser.
#
# PostgreSQL exempts a SUPERUSER from row-level security entirely. `FORCE ROW
# LEVEL SECURITY` does not close this: FORCE covers the table OWNER, and says
# nothing about superusers. Until VER-001 this script ran every isolation test
# as `lacteva`, which the official postgres image creates as a superuser — so
# steps 2 and 3 were checking that policies EXIST while proving nothing about
# whether they are ENFORCED. The suite would have been green with every policy
# silently inert.
APP_USER="${APP_USER:-lacteva_app}"
APP_PASSWORD="${APP_PASSWORD:-lacteva_app_proof}"

SOURCE_DB="${SOURCE_DB:-lacteva_proof}"
RESTORE_DB="${RESTORE_DB:-lacteva_restore}"
# DEMO-013: its own database, because it must start at an OLDER revision than
# the others and would otherwise contaminate the source the proof restores.
BACKFILL_DB="${BACKFILL_DB:-lacteva_backfill}"
#: The revision immediately before DEMO-013 — the state production was in when
#: the migration met it. Pinned rather than computed: this step is about one
#: specific backfill, and a moving target would silently stop testing it.
BACKFILL_FROM="${BACKFILL_FROM:-e91b6c47a2d8}"
# Step 3's suites get a database of their OWN. They are tests: they fabricate
# settlements with no lines and payments that are meant to lose a race, and
# they commit that residue. Run them in ${SOURCE_DB} and step 8's deep
# integrity check reads their leftovers as corruption — which is exactly what
# it should say about them, and exactly what it must not say about the dairy
# the API seeded. Separating the databases keeps both statements true.
TESTS_DB="${TESTS_DB:-lacteva_pgtests}"
WORKDIR="$(mktemp -d)"
BACKUP_DIR="${WORKDIR}/backup"

# Run from the service root regardless of where the script was invoked.
cd "$(dirname "${BASH_SOURCE[0]}")/../../services/platform-core"

# `${RUN-...}` without the colon, so an explicitly EMPTY RUN is honoured:
# `verify-postgres.sh` sets it that way when uv is absent and the virtualenv
# on PATH already has the dependencies. With `:-` an empty value would fall
# back to uv and the run would fail with "uv: command not found".
RUN="${RUN-uv run}"

# A leading '/' in PGHOST is a unix SOCKET directory, not a hostname. libpq
# understands that directly; a SQLAlchemy URL has to carry it as a query
# parameter, since the authority section cannot hold a path. This is the shape
# `verify-postgres.sh` produces when it starts a local cluster, and the shape
# most system PostgreSQL installations offer by default.
dsn_for() {
  local user="$1" password="$2" database="$3"
  if [ "${PGHOST#/}" != "${PGHOST}" ]; then
    echo "postgresql+asyncpg://${user}@/${database}?host=${PGHOST}"
  else
    echo "postgresql+asyncpg://${user}:${password}@${PGHOST}:${PGPORT}/${database}"
  fi
}
# The OWNER url — migrations, backup and restore, which need DDL.
url_for() { dsn_for "${PGUSER}" "${PGPASSWORD}" "$1"; }
# The APPLICATION url — everything whose result depends on RLS being enforced.
app_url_for() { dsn_for "${APP_USER}" "${APP_PASSWORD}" "$1"; }
psql_do() { psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "$1" -tAc "$2"; }

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mPROOF FAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# OPS-001: publish a summary where the operator will actually see it. Under
# GitHub Actions that is the job summary page; locally it is stdout, so the
# same lines serve both without a second code path.
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
summary() { printf '%s\n' "$*" >> "${SUMMARY}"; }

# Teardown. The working directory always goes; the throwaway databases go too
# unless KEEP_DATABASES=1, because a failed run is much easier to diagnose
# with the database still standing.
cleanup() {
  local status=$?
  rm -rf "${WORKDIR}"
  if [ "${KEEP_DATABASES:-0}" != "1" ]; then
    psql_do postgres "DROP DATABASE IF EXISTS ${SOURCE_DB}" >/dev/null 2>&1 || true
    psql_do postgres "DROP DATABASE IF EXISTS ${RESTORE_DB}" >/dev/null 2>&1 || true
    psql_do postgres "DROP DATABASE IF EXISTS ${TESTS_DB}" >/dev/null 2>&1 || true
    psql_do postgres "DROP DATABASE IF EXISTS ${BACKFILL_DB}" >/dev/null 2>&1 || true
  else
    printf '\nKEEP_DATABASES=1 — %s, %s and %s left in place for inspection.\n' \
      "${SOURCE_DB}" "${RESTORE_DB}" "${TESTS_DB}"
  fi
  return "${status}"
}
trap cleanup EXIT

# The seeder and CLI must not start background loops: their sessions would
# interleave with the work being measured. Consumers are driven explicitly.
export LACTEVA_ENV=staging
export LACTEVA_EVENT_BUS=memory
export LACTEVA_OUTBOX_MODE=inline
export LACTEVA_CONSUMERS_ENABLED=false
export LACTEVA_RATE_LIMIT_BACKEND=memory
export LACTEVA_MINIO_SECRET_KEY=proof-not-a-real-secret
# OPS-001: a skipped PostgreSQL proof is worse than an absent one, because it
# is green. With this set, the suites raise at collection instead of skipping,
# so a misconfigured job cannot report success for work that never happened.
export LACTEVA_REQUIRE_POSTGRES=1

step "0/9  waiting for PostgreSQL at ${PGHOST}:${PGPORT}"
for _ in $(seq 1 60); do
  pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" >/dev/null 2>&1 && break
  sleep 1
done
pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" >/dev/null 2>&1 \
  || fail "PostgreSQL never became ready"
PG_VERSION="$(psql_do postgres "SHOW server_version")"
echo "    PostgreSQL ${PG_VERSION}"

step "1/9  migrations apply to an EMPTY database (${SOURCE_DB})"
psql_do postgres "DROP DATABASE IF EXISTS ${SOURCE_DB}" >/dev/null
psql_do postgres "CREATE DATABASE ${SOURCE_DB}" >/dev/null
LACTEVA_DATABASE_URL="$(url_for "${SOURCE_DB}")" ${RUN} alembic upgrade head \
  || fail "migrations did not apply to an empty database"
TABLES="$(psql_do "${SOURCE_DB}" \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
echo "    ${TABLES} tables created"
[ "${TABLES}" -gt 40 ] || fail "only ${TABLES} tables after migration — expected the full schema"

# DEMO-013: migrations meeting EXISTING DATA, which step 1 cannot show.
#
# An empty database proves a migration parses and its DDL applies. It says
# nothing about a BACKFILL, because there is nothing to back-fill — and the
# production case is always the other one. DEMO-013's migration passed every
# SQLite test and every empty-database run, then failed on the real deployment
# with
#
#     column "supported_languages" is of type json
#     but expression is of type character varying
#
# because a hand-written UPDATE bound a pre-serialized JSON string, which is
# exactly right for SQLite's TEXT column and refused by PostgreSQL at parse
# time. This step migrates to the revision BEFORE, inserts organizations, then
# upgrades — so a backfill is proved against rows rather than against nothing.
step "1b/9  migrations back-fill EXISTING rows (${BACKFILL_DB})"
psql_do postgres "DROP DATABASE IF EXISTS ${BACKFILL_DB}" >/dev/null
psql_do postgres "CREATE DATABASE ${BACKFILL_DB}" >/dev/null
BACKFILL_URL="$(url_for "${BACKFILL_DB}")"
LACTEVA_DATABASE_URL="${BACKFILL_URL}" ${RUN} alembic upgrade "${BACKFILL_FROM}" >/dev/null   || fail "could not migrate to ${BACKFILL_FROM}"
# Lower case on purpose: the column has always held whatever was posted, and
# the backfill matches on upper(country_code).
psql_do "${BACKFILL_DB}" "
  INSERT INTO organization (id, name, slug, country_code, org_type, status, default_locale, created_at)
  VALUES (gen_random_uuid(), 'Proof Kenya', 'proof-ke', 'ke', 'cooperative', 'active', 'en', now()),
         (gen_random_uuid(), 'Proof Unlisted', 'proof-zz', 'ZZ', 'cooperative', 'active', 'en', now())" >/dev/null
LACTEVA_DATABASE_URL="${BACKFILL_URL}" ${RUN} alembic upgrade head >/dev/null   || fail "migrations failed against existing rows — the production case"
BACKFILLED="$(psql_do "${BACKFILL_DB}"   "SELECT currency_code || ' ' || timezone || ' ' || supported_languages::text
     FROM organization WHERE slug = 'proof-ke'")"
[ "${BACKFILLED}" = 'KES Africa/Nairobi ["en-KE", "sw-KE"]' ]   || fail "Kenya back-filled as '${BACKFILLED}'"
# An unlisted country gets ISO 4217's "no currency", never a guess at somebody
# else's money.
UNLISTED="$(psql_do "${BACKFILL_DB}"   "SELECT currency_code || ' ' || timezone FROM organization WHERE slug = 'proof-zz'")"
[ "${UNLISTED}" = "XXX UTC" ] || fail "an unlisted country back-filled as '${UNLISTED}'"
NULLS="$(psql_do "${BACKFILL_DB}"   "SELECT count(*) FROM organization
    WHERE currency_code IS NULL OR timezone IS NULL OR supported_languages IS NULL")"
[ "${NULLS}" = "0" ] || fail "${NULLS} organizations left without a locale"
echo "    back-filled 2 pre-existing organizations, 0 nulls"

# VER-001: create the unprivileged role the isolation proof runs as, and
# prove it is unprivileged. Everything after this point that reads or writes
# tenant data connects as ${APP_USER}.
psql_do postgres "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_USER}') THEN
    CREATE ROLE ${APP_USER} LOGIN PASSWORD '${APP_PASSWORD}';
  END IF;
END \$\$" >/dev/null
psql_do postgres "ALTER ROLE ${APP_USER} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE" >/dev/null
grant_app_access() {
  psql_do "$1" "
    GRANT CONNECT ON DATABASE $1 TO ${APP_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_USER};
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${APP_USER};
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${APP_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${APP_USER};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${APP_USER};" >/dev/null
}
grant_app_access "${SOURCE_DB}"

BYPASSES="$(psql_do "${SOURCE_DB}" \
  "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = '${APP_USER}'")"
[ "${BYPASSES}" = "f" ] \
  || fail "${APP_USER} is SUPERUSER or has BYPASSRLS — every isolation test below would pass vacuously"
echo "    application role ${APP_USER}: NOSUPERUSER, NOBYPASSRLS"

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

step "3/9  PostgreSQL-only test suites (RLS enforcement + exact aggregation)"
# In ${TESTS_DB}, not ${SOURCE_DB} — see the TESTS_DB comment at the top. The
# schema arrives the same way it did in step 1, so the suites still run against
# migrated tables with every policy forced.
psql_do postgres "DROP DATABASE IF EXISTS ${TESTS_DB}" >/dev/null
psql_do postgres "CREATE DATABASE ${TESTS_DB}" >/dev/null
LACTEVA_DATABASE_URL="$(url_for "${TESTS_DB}")" ${RUN} alembic upgrade head \
  || fail "migrations did not apply to the test database"
grant_app_access "${TESTS_DB}"
echo "    suites run in ${TESTS_DB}; ${SOURCE_DB} carries only what the API seeds"
RLS_LOG="${WORKDIR}/pg-tests.log"
JUNIT="${WORKDIR}/pg-tests.xml"
# Every suite that can only be evaluated on a real engine, in one run:
#   RLS            — policies, coverage, and the pre-tenant flows (SEC-001/002)
#   aggregation    — float summation is order-dependent and a scaled numeric
#                    column rounds on store; SQLite exhibits neither (DB-002)
#   recovery       — backup/restore correctness: a `time` column that broke
#                    every backup, a schema revision read from
#                    `alembic_version`, and isolation on restored rows (DR-001)
#   concurrency    — the money path under real contention: the settlement lock
#                    that stops a double payment, the lock ORDER that stops it
#                    deadlocking, the tenant filter on the allocation sum, and
#                    document-number allocation. `FOR UPDATE` is a no-op on
#                    SQLite, so the main suite could only ever grep for it
#                    (ARCH-FINAL-001, extended by PROD-001)
#   worker races   — two consumer runners on one database, which is what a
#                    second API replica IS. Advisory locks and savepoint
#                    upserts are PostgreSQL behaviour (DEPLOY-001)
#   price storage  — `unit_price` is NUMERIC(12,4), not float. SQLite has no
#                    numeric type with a declared scale, so it would accept
#                    every assertion while storing a float (DEPLOY-001)
# Add new PostgreSQL-only modules HERE, not to a second job — this is the list
# the skip assertion below protects.
#
# DEMO-020: `test_business_date_sql_postgres.py` was added by DEMO-019 and
# never added to this line, so the proof it exists for had never run in the
# pipeline — it passed only when someone ran it by hand. The skip assertion
# below cannot catch that, because a file that is never named is never
# collected and therefore never skipped. `test_no_postgres_suite_is_left_out`
# in tests/test_production_readiness.py now compares this list against the
# files on disk, which is the check that would have caught it — and which
# found a SECOND absent suite the moment it was written:
# `test_scheduler_concurrency_postgres.py`, DEMO-018's four-worker race proof.
LACTEVA_TEST_POSTGRES_URL="$(app_url_for "${TESTS_DB}")" \
  LACTEVA_TEST_POSTGRES_ADMIN_URL="$(url_for "${TESTS_DB}")" \
  ${RUN} pytest tests/test_rls_postgres.py tests/test_exact_aggregation_postgres.py \
  tests/test_disaster_recovery_postgres.py tests/test_payment_concurrency_postgres.py \
  tests/test_consumer_concurrency_postgres.py tests/test_pricing_precision_postgres.py \
  tests/test_business_date_sql_postgres.py tests/test_business_calendar_postgres.py \
  tests/test_scheduler_concurrency_postgres.py tests/test_period_guard_postgres.py \
  tests/test_message_idempotency_postgres.py \
  tests/test_subscription_concurrency_postgres.py \
  tests/test_subscription_payment_concurrency_postgres.py \
  tests/test_statement_delivery_postgres.py \
  -v --no-header -rs --junitxml="${JUNIT}" 2>&1 | tee "${RLS_LOG}" \
  || fail "PostgreSQL-only tests failed"

# The skip assertion, from structured output rather than from prose. pytest's
# summary line has changed format before; the JUnit counts have not. This is a
# backstop — LACTEVA_REQUIRE_POSTGRES=1 already makes a skip a collection
# error — but a guarantee worth having twice is worth asserting twice.
[ -s "${JUNIT}" ] || fail "pytest produced no JUnit report at ${JUNIT} — the run did not happen"
PG_COUNTS="$(${RUN} python - "${JUNIT}" <<'PYCHECK'
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
suites = root.iter("testsuite") if root.tag == "testsuites" else [root]
tests = skipped = failures = errors = 0
for s in suites:
    tests += int(s.get("tests", 0)); skipped += int(s.get("skipped", 0))
    failures += int(s.get("failures", 0)); errors += int(s.get("errors", 0))
print(f"{tests} {skipped} {failures} {errors}")
PYCHECK
)"
read -r PG_TESTS PG_SKIPPED PG_FAILURES PG_ERRORS <<<"${PG_COUNTS}"
[ -n "${PG_TESTS}" ] || fail "could not read test counts from ${JUNIT}"
[ "${PG_SKIPPED}" = "0" ] \
  || fail "${PG_SKIPPED} PostgreSQL test(s) SKIPPED — a green skip is not a proof"
[ "${PG_FAILURES}" = "0" ] && [ "${PG_ERRORS}" = "0" ] \
  || fail "${PG_FAILURES} failure(s), ${PG_ERRORS} error(s) in the PostgreSQL suites"
[ "${PG_TESTS}" -gt 0 ] || fail "no PostgreSQL tests were collected at all"
echo "    ${PG_TESTS} PostgreSQL-only tests ran, 0 skipped"

step "4/9  seeding a real dairy through the platform's own API"
LACTEVA_DATABASE_URL="$(app_url_for "${SOURCE_DB}")" \
  ${RUN} python ../../infra/ci/seed_proof_data.py "${WORKDIR}/seed.json" \
  || fail "seeding failed"
[ -s "${WORKDIR}/seed.json" ] || fail "the seeder wrote no summary"
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

# --- the published summary ------------------------------------------------
# Under GitHub Actions this lands on the job summary page, so an operator sees
# what was proven without opening the log. Locally it prints to stdout.
summary "## PostgreSQL verification — passed"
summary ""
summary "**Server:** PostgreSQL \`${PG_VERSION}\`"
summary ""
summary "| Step | Proven | Evidence |"
summary "| --- | --- | --- |"
summary "| 1 | Migrations apply to an **empty** database | ${TABLES} tables created |"
summary "| 2 | RLS enabled **and forced**, and covering | ${PROTECTED} tables forced, ${POLICIES} policies, 0 tenant_id tables uncovered |"
summary "| 3 | PostgreSQL-only suites pass, none skipped | ${PG_TESTS} tests, ${PG_SKIPPED} skipped |"
SEED_FACTS="$(${RUN} python -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(', '.join(f'{k} {v}' for k, v in d.items() if k != 'organization'))
" "${WORKDIR}/seed.json")"
summary "| 4 | A real dairy seeds through the platform's own API | ${SEED_FACTS} |"
summary "| 5 | Logical backup verifies against its own checksums | see log |"
summary "| 6 | A **second, fresh** database migrates | \`${RESTORE_DB}\` |"
summary "| 7 | Restore into it succeeds | see log |"
summary "| 8 | Restored data passes deep business integrity | settlements, payments, receipts, projections |"
summary "| 9 | Source and restored compared fact by fact | identical |"
summary ""
summary "_Run \`docker compose -f docker-compose.proof.yml run --rm proof\` to reproduce this locally — it is the same script._"

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
