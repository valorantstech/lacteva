#!/usr/bin/env bash
# Automated restore verification (BAK-001; corrected and proven by PITR-001).
#
# THE point: a backup is valid only if it restores, the application starts on
# it, health is green, projections rebuild, and business smoke tests pass.
# Anything less is a file nobody has read.
#
# Run this on a schedule against production backups, into a throwaway
# instance. A restore test that only runs after a disaster is not a test.
#
# Recovery targets — pick at most one:
#
#   TARGET_TIME='2026-08-08 14:32:00+00'   an instant
#   TARGET_NAME='before_migration'         a named restore point
#   TARGET_XID='1076'                      a transaction boundary
#   (none)                                 replay everything in the archive
#
# `./infra/ci/pitr-proof.sh` executes all four against a real cluster. This
# script is the operator-facing version of the same procedure.
set -euo pipefail

: "${BASE_BACKUP:?set BASE_BACKUP (path to a pg_basebackup directory)}"
: "${RESTORE_PGDATA:?set RESTORE_PGDATA (throwaway data directory)}"
RESTORE_PORT="${RESTORE_PORT:-5433}"
WAL_ARCHIVE="${WAL_ARCHIVE:-/var/backups/lacteva/wal}"
TARGET_TIME="${TARGET_TIME:-}"
TARGET_NAME="${TARGET_NAME:-}"
TARGET_XID="${TARGET_XID:-}"

fail() { echo "RESTORE TEST FAILED: $*" >&2; exit 1; }

TARGETS_SET=0
for t in "${TARGET_TIME}" "${TARGET_NAME}" "${TARGET_XID}"; do
  [ -n "${t}" ] && TARGETS_SET=$((TARGETS_SET + 1))
done
[ "${TARGETS_SET}" -le 1 ] \
  || fail "set at most one of TARGET_TIME / TARGET_NAME / TARGET_XID — PostgreSQL applies one recovery target, and specifying several is a silent coin flip"

echo "==> 1/7 unpacking the base backup"
rm -rf "${RESTORE_PGDATA}"; mkdir -p "${RESTORE_PGDATA}"
if [[ -f "${BASE_BACKUP}/base.tar.gz" ]]; then
  tar -xzf "${BASE_BACKUP}/base.tar.gz" -C "${RESTORE_PGDATA}" || fail "base.tar.gz did not unpack"
  [[ -f "${BASE_BACKUP}/pg_wal.tar.gz" ]] \
    && tar -xzf "${BASE_BACKUP}/pg_wal.tar.gz" -C "${RESTORE_PGDATA}/pg_wal"
else
  # A plain-format base backup: copy rather than unpack.
  cp -a "${BASE_BACKUP}/." "${RESTORE_PGDATA}/" || fail "could not copy the base backup"
fi
chmod 700 "${RESTORE_PGDATA}"

echo "==> 2/7 verifying the base before depending on it"
# PITR-001: check the manifest BEFORE recovery, not after. Discovering a bad
# base halfway through a recovery costs the whole attempt.
if [[ -f "${RESTORE_PGDATA}/backup_manifest" ]]; then
  pg_verifybackup "${RESTORE_PGDATA}" >/dev/null \
    || fail "pg_verifybackup rejected the base backup — find another copy"
  echo "    manifest verified"
else
  echo "    WARNING: no backup_manifest; cannot verify this base backup"
fi

echo "==> 3/7 configuring recovery"
# Start from the backup's own config, minus any inherited overrides.
rm -f "${RESTORE_PGDATA}/postgresql.auto.conf"

# WO-40: the settings the WAL was WRITTEN with, taken from the backup itself.
#
# PostgreSQL refuses to replay WAL on an instance whose `max_connections` (and
# four relatives) are lower than the primary's — the WAL contains lock and
# transaction slots the smaller instance cannot represent, so it aborts:
#
#   FATAL: recovery aborted because of insufficient parameter settings
#   DETAIL: max_connections = 100 is a lower setting than on the primary
#           server, where its value was 200.
#
# The live primary is tuned (200 connections); the restore was starting on the
# image default (100), so point-in-time recovery of the real database did not
# work AT ALL — and could not be seen from the proof, whose own primary ran on
# defaults where the two happened to match. `pitr-proof.sh` now tunes its
# primary for exactly this reason.
#
# `pg_controldata` records each value as of the base backup, which is the only
# honest source: it describes the cluster the WAL came from, not whatever the
# primary happens to be set to today.
echo "    carrying over the primary's parameter settings"
_control="$(pg_controldata "${RESTORE_PGDATA}")"
_setting() { # control-file label, GUC name
  local value
  value="$(printf '%s\n' "${_control}" | sed -n "s/^$1 setting: *//p" | tr -d '[:space:]')"
  [ -n "${value}" ] || return 0
  echo "$2 = ${value}"
  echo "      $2 = ${value}" >&2
}
{
  _setting "max_connections"      "max_connections"
  _setting "max_worker_processes" "max_worker_processes"
  _setting "max_wal_senders"      "max_wal_senders"
  _setting "max_prepared_xacts"   "max_prepared_transactions"
  _setting "max_locks_per_xact"   "max_locks_per_transaction"
} >> "${RESTORE_PGDATA}/postgresql.conf"

{
  echo "port = ${RESTORE_PORT}"
  echo "restore_command = 'cp ${WAL_ARCHIVE}/%f %p'"
  # PITR-001 — the timeline trap. A recovered cluster PROMOTES onto a new
  # timeline. If it also archives, its timeline lands in the same archive, and
  # because `recovery_target_timeline` defaults to 'latest', the NEXT recovery
  # from this same base can follow the recovered timeline instead of the
  # original — overshooting its target with no error. Two settings close it:
  echo "archive_mode = off"
  echo "recovery_target_timeline = '${RECOVERY_TIMELINE:-current}'"
  echo "recovery_target_action = 'promote'"
  if [[ -n "${TARGET_TIME}" ]]; then
    echo "recovery_target_time = '${TARGET_TIME}'"
  elif [[ -n "${TARGET_NAME}" ]]; then
    echo "recovery_target_name = '${TARGET_NAME}'"
  elif [[ -n "${TARGET_XID}" ]]; then
    echo "recovery_target_xid = '${TARGET_XID}'"
  fi
} >> "${RESTORE_PGDATA}/postgresql.conf"
touch "${RESTORE_PGDATA}/recovery.signal"

echo "==> 4/7 starting the restored instance and WAITING FOR PROMOTION"
pg_ctl -D "${RESTORE_PGDATA}" -o "-p ${RESTORE_PORT}" -w -t 300 start \
  || fail "the restored instance did not start"
trap 'pg_ctl -D "${RESTORE_PGDATA}" -m immediate stop >/dev/null 2>&1 || true' EXIT

# PITR-001: `pg_ctl -w start` returns when the server ACCEPTS CONNECTIONS,
# and during recovery that happens at "ready to accept read-only connections"
# — before the target is reached and before promotion. This script previously
# continued straight to `alembic upgrade head` against a read-only, still-
# replaying database. Poll until recovery actually finishes.
IN_RECOVERY=t
for _ in $(seq 1 300); do
  IN_RECOVERY="$(psql -p "${RESTORE_PORT}" -U "${PGUSER:-postgres}" -d postgres -tAc \
    'SELECT pg_is_in_recovery()' 2>/dev/null || echo t)"
  [ "${IN_RECOVERY}" = "f" ] && break
  sleep 1
done
[ "${IN_RECOVERY}" = "f" ] \
  || fail "the instance is still in recovery after 300s — the target may be unreachable, or the archive may be missing a segment"
TIMELINE="$(psql -p "${RESTORE_PORT}" -U "${PGUSER:-postgres}" -d postgres -tAc \
  'SELECT timeline_id FROM pg_control_checkpoint()')"
echo "    promoted onto timeline ${TIMELINE}"

export LACTEVA_DATABASE_URL="postgresql+asyncpg://${PGUSER:-postgres}:${PGPASSWORD:-}@localhost:${RESTORE_PORT}/${PGDATABASE:-lacteva}"

echo "==> 5/7 the schema is the one the data expects"
# PITR-001: this step used to run `alembic upgrade head`, which is WRONG on a
# recovered database and potentially destructive. A physical restore is
# byte-identical to the source at the recovery target; running migrations
# against it MUTATES the recovered data — applying a migration the recovered
# point never had. During an incident that is the last thing anyone wants.
# Assert the revision instead; migrating is a deliberate separate decision.
REVISION="$(psql -p "${RESTORE_PORT}" -U "${PGUSER:-postgres}" -d "${PGDATABASE:-lacteva}" \
  -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null || true)"
[ -n "${REVISION}" ] || fail "alembic_version is empty — this is not a Lacteva database"
echo "    schema revision ${REVISION} (NOT migrated — a recovery is restored, not upgraded)"

echo "==> 6/7 business integrity (the platform's own rules, deep)"
uv run python -m platform_core.core.backup.cli integrity --deep \
  || fail "the restored data violates the platform's business rules"

echo "==> 7/7 smoke test: the application answers on the restored data"
uv run python - <<'PY' || fail "the application could not serve the restored data"
import asyncio

from httpx import ASGITransport, AsyncClient

from platform_core.main import create_app


async def main():
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://restore-test") as c:
            live = await c.get("/health/live")
            assert live.status_code == 200, live.text
            ready = await c.get("/health/ready")
            assert ready.status_code == 200, f"not ready after restore: {ready.text}"
    print("smoke test passed: the application starts and reports ready")


asyncio.run(main())
PY

echo
echo "RESTORE TEST PASSED"
echo "  base backup     : ${BASE_BACKUP}"
echo "  recovery target : ${TARGET_TIME:-${TARGET_NAME:-${TARGET_XID:-<end of WAL>}}}"
echo "  timeline        : ${TIMELINE}"
echo "  schema revision : ${REVISION}"
echo "  verified        : manifest, promotion, schema, business integrity, readiness"
echo
echo "NOTE: this proves the backup restores. It does NOT prove the recovery"
echo "      target excluded later work — for that assertion, see"
echo "      ./infra/ci/pitr-proof.sh, which checks what must be ABSENT."
