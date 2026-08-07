#!/usr/bin/env bash
# Disaster recovery proof (DR-001).
#
#     ./infra/ci/dr-proof.sh
#
# Executes the full recovery pipeline against real PostgreSQL, ending in a
# fact-for-fact comparison between the source and the recovered system:
#
#    1. a fresh instance, migrated from empty
#    2. a realistic dairy seeded through the platform's own API
#    3. real business activity — collections, settlements, payments,
#       receipts, notifications, projections
#    4. a logical backup
#    5. backup integrity verified against its own checksums
#    6. a SECOND, SEPARATE instance, migrated from empty
#    7. the backup restored into it
#    8. every business integrity check, deep
#    9. source vs restored, fact for fact, table by table
#   10. the recovery hardening checks: a corrupt backup is refused, a schema
#       mismatch is refused, and the restored data is still tenant-isolated
#
# Two SEPARATE clusters, not two databases on one. Recovery means the original
# machine is gone; proving it on the same instance quietly assumes the thing
# that failed still works.
#
# Any failure fails the build.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

SOURCE_DIR="${SOURCE_DIR:-/tmp/lacteva-dr-source}"
RESTORE_DIR="${RESTORE_DIR:-/tmp/lacteva-dr-restore}"
SOURCE_DB="${SOURCE_DB:-dr_source}"
RESTORE_DB="${RESTORE_DB:-dr_restore}"
APP_USER="${APP_USER:-lacteva_app}"
APP_PASSWORD="${APP_PASSWORD:-dr_proof}"
WORKDIR="$(mktemp -d)"
BACKUP_DIR="${WORKDIR}/backup"

PYTHON="${PYTHON:-services/platform-core/.venv/bin/python}"
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3)"
PYTHON="$(cd "$(dirname "${PYTHON}")" && pwd)/$(basename "${PYTHON}")"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mDR PROOF FAILED: %s\033[0m\n' "$*" >&2; exit 1; }
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
summary() { printf '%s\n' "$*" >> "${SUMMARY}"; }

cleanup() {
  local status=$?
  rm -rf "${WORKDIR}"
  if [ "${KEEP_INSTANCES:-0}" = "1" ]; then
    printf '\nKEEP_INSTANCES=1 — %s and %s left running.\n' "${SOURCE_DIR}" "${RESTORE_DIR}"
  fi
  return "${status}"
}
trap cleanup EXIT

# The seeder and CLI must not start background loops: their sessions would
# interleave with the activity being measured. Consumers are driven explicitly.
export LACTEVA_ENV=staging
export LACTEVA_EVENT_BUS=memory
export LACTEVA_OUTBOX_MODE=inline
export LACTEVA_CONSUMERS_ENABLED=false
export LACTEVA_RATE_LIMIT_BACKEND=memory
export LACTEVA_MINIO_SECRET_KEY=dr-proof-not-a-real-secret
export LACTEVA_REQUIRE_POSTGRES=1

url() { echo "postgresql+asyncpg://postgres@/$2?host=$1"; }
app_url() { echo "postgresql+asyncpg://${APP_USER}:${APP_PASSWORD}@/$2?host=$1"; }

# --- instances ---------------------------------------------------------------
step "0/10  two separate PostgreSQL instances"
rm -rf "${SOURCE_DIR}" "${RESTORE_DIR}"
"${PYTHON}" - "${SOURCE_DIR}" "${SOURCE_DB}" "${RESTORE_DIR}" "${RESTORE_DB}" <<'PYEOF'
import pathlib, sys
import pgserver

for datadir, dbname in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    path = pathlib.Path(datadir)
    path.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(path, cleanup_mode=None)
    server.psql(f"CREATE DATABASE {dbname}")
    version = server.psql("SHOW server_version").split("\n")[2].strip()
    print(f"    {datadir}  PostgreSQL {version}  database {dbname}")
PYEOF

cd services/platform-core

# --- 1. migrations -----------------------------------------------------------
step "1/10  migrations apply to an EMPTY source instance"
LACTEVA_DATABASE_URL="$(url "${SOURCE_DIR}" "${SOURCE_DB}")" "${PYTHON}" -m alembic upgrade head \
  >/dev/null 2>&1 || fail "migrations did not apply to the source instance"
echo "    source migrated"

# --- 2/3. seed + business activity ------------------------------------------
step "2/10  a realistic dairy, seeded through the platform's own API"
step "3/10  business activity: collections, settlements, payments, receipts, notifications"
LACTEVA_DATABASE_URL="$(url "${SOURCE_DIR}" "${SOURCE_DB}")" \
  "${PYTHON}" ../../infra/ci/seed_proof_data.py "${WORKDIR}/seed.json" >/dev/null 2>&1 \
  || fail "seeding failed"
[ -s "${WORKDIR}/seed.json" ] || fail "the seeder wrote no summary"
"${PYTHON}" -c "
import json, sys
d = json.load(open(sys.argv[1]))
print('    ' + ', '.join(f'{k}={v}' for k, v in d.items() if k != 'organization'))
" "${WORKDIR}/seed.json"

# --- 4. backup ---------------------------------------------------------------
step "4/10  logical backup"
LACTEVA_DATABASE_URL="$(url "${SOURCE_DIR}" "${SOURCE_DB}")" \
  "${PYTHON}" -m platform_core.core.backup.cli backup "${BACKUP_DIR}" >/dev/null 2>&1 \
  || fail "backup failed"
"${PYTHON}" -c "
import json
m = json.load(open('${BACKUP_DIR}/manifest.json'))
print(f\"    {len(m['tables'])} tables, {sum(t['rows'] for t in m['tables'])} rows, \"
      f\"schema {m['schema_revision'] or 'UNKNOWN'}\")
assert m['schema_revision'], 'the manifest records no schema revision'
"

# --- 5. verify ---------------------------------------------------------------
step "5/10  backup verified against its own checksums"
LACTEVA_DATABASE_URL="$(url "${SOURCE_DIR}" "${SOURCE_DB}")" \
  "${PYTHON}" -m platform_core.core.backup.cli verify "${BACKUP_DIR}" >/dev/null 2>&1 \
  || fail "the backup does not verify against its own checksums"
echo "    every table matches its checksum"

# --- 6. second instance ------------------------------------------------------
step "6/10  a SECOND, SEPARATE instance, migrated from empty"
LACTEVA_DATABASE_URL="$(url "${RESTORE_DIR}" "${RESTORE_DB}")" "${PYTHON}" -m alembic upgrade head \
  >/dev/null 2>&1 || fail "migrations did not apply to the restore instance"
# The unprivileged role the application connects as (VER-001): the isolation
# assertions below are vacuous as a superuser.
"${PYTHON}" - "${RESTORE_DIR}" "${RESTORE_DB}" "${APP_USER}" "${APP_PASSWORD}" <<'PYEOF'
import asyncio, sys
import asyncpg

async def main():
    host, db, user, password = sys.argv[1:5]
    conn = await asyncpg.connect(user="postgres", database=db, host=host)
    await conn.execute(f"DROP ROLE IF EXISTS {user}")
    await conn.execute(
        f"CREATE ROLE {user} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS"
    )
    await conn.execute(f"""
        GRANT USAGE ON SCHEMA public TO {user};
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {user};
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {user};""")
    await conn.close()

asyncio.run(main())
PYEOF
echo "    restore target migrated; application role ${APP_USER} is NOSUPERUSER/NOBYPASSRLS"

# --- 7/8. restore + deep integrity ------------------------------------------
step "7/10  restore into the second instance"
step "8/10  deep business integrity on the restored data"
LACTEVA_DATABASE_URL="$(url "${RESTORE_DIR}" "${RESTORE_DB}")" \
  "${PYTHON}" -m platform_core.core.backup.cli restore "${BACKUP_DIR}" \
  > "${WORKDIR}/restore.json" 2>/dev/null \
  || fail "restore or its integrity verification failed"
# The CLI writes its structured log to stdout alongside the result, so the
# payload is the last top-level JSON object rather than the whole stream.
"${PYTHON}" - "${WORKDIR}/restore.json" <<'PYEOF' || fail "restored data did not pass business integrity"
import json, sys

lines = open(sys.argv[1]).read().splitlines()
start = max(i for i, line in enumerate(lines) if line == "{")
report = json.loads("\n".join(lines[start:]))
failed = [c["name"] for c in report["checks"] if not c["passed"]]
assert not failed, f"integrity checks failed: {failed}"
print(f"    {report['rows']} rows restored; {len(report['checks'])} integrity checks passed")
PYEOF

# --- 9. fact-for-fact --------------------------------------------------------
step "9/10  source vs restored, fact for fact"
"${PYTHON}" ../../infra/ci/dr_compare.py \
  "$(url "${SOURCE_DIR}" "${SOURCE_DB}")" \
  "$(url "${RESTORE_DIR}" "${RESTORE_DB}")" 2>/dev/null \
  || fail "the restored system does not hold the same facts as its source"

# --- 10. recovery hardening --------------------------------------------------
step "10/10  recovery hardening: corruption, schema drift, isolation"
LACTEVA_TEST_POSTGRES_URL="$(app_url "${RESTORE_DIR}" "${RESTORE_DB}")" \
LACTEVA_TEST_POSTGRES_ADMIN_URL="$(url "${RESTORE_DIR}" "${RESTORE_DB}")" \
  "${PYTHON}" -m pytest tests/test_disaster_recovery_postgres.py \
  -q --no-header --junitxml="${WORKDIR}/dr-tests.xml" >/dev/null 2>&1 \
  || fail "the disaster recovery test suite failed"
DR_COUNTS="$("${PYTHON}" - "${WORKDIR}/dr-tests.xml" <<'PYCHECK'
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
read -r DR_TESTS DR_SKIPPED DR_FAILURES DR_ERRORS <<<"${DR_COUNTS}"
[ "${DR_SKIPPED}" = "0" ] || fail "${DR_SKIPPED} recovery test(s) SKIPPED — a green skip is not a proof"
[ "${DR_FAILURES}" = "0" ] && [ "${DR_ERRORS}" = "0" ] || fail "recovery tests failed"
[ "${DR_TESTS}" -gt 0 ] || fail "no recovery tests were collected at all"
echo "    ${DR_TESTS} recovery tests ran, 0 skipped"

# --- summary -----------------------------------------------------------------
summary "## Disaster recovery — proven"
summary ""
summary "| Step | Proven |"
summary "| --- | --- |"
summary "| 1 | Migrations apply to an empty instance |"
summary "| 2-3 | A realistic dairy with real business activity, through the platform's own API |"
summary "| 4-5 | Logical backup, verified against its own checksums |"
summary "| 6 | A **second, separate** instance migrated from empty |"
summary "| 7-8 | Restored, and the restored data passes deep business integrity |"
summary "| 9 | Source and restored hold the same facts, table by table |"
summary "| 10 | Corruption refused, schema drift refused, tenant isolation intact (${DR_TESTS} tests) |"

cat <<'BANNER'

╭──────────────────────────────────────────────────────────────╮
│  DISASTER RECOVERY PROVEN                                    │
│                                                              │
│  migrations from empty ........ proven                       │
│  realistic dairy + activity ... proven                       │
│  backup + checksums ........... proven                       │
│  SECOND instance restore ...... proven                       │
│  deep business integrity ...... proven                       │
│  source vs restored ........... fact for fact                │
│  corrupt backup ............... refused                      │
│  schema drift ................. refused                      │
│  tenant isolation after restore  enforced                    │
╰──────────────────────────────────────────────────────────────╯
BANNER
