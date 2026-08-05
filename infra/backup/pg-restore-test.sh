#!/usr/bin/env bash
# Automated restore verification (BAK-001).
#
# THE point of this work order: a backup is valid only if it restores, the
# application starts on it, health is green, projections rebuild, and business
# smoke tests pass. Anything less is a file nobody has read.
#
# Run this on a schedule against production backups, into a throwaway
# instance. A restore test that only runs after a disaster is not a test.
set -euo pipefail

: "${BASE_BACKUP:?set BASE_BACKUP (path to a pg_basebackup directory)}"
: "${RESTORE_PGDATA:?set RESTORE_PGDATA (throwaway data directory)}"
RESTORE_PORT="${RESTORE_PORT:-5433}"
TARGET_TIME="${TARGET_TIME:-}"   # optional: PITR to this instant

fail() { echo "RESTORE TEST FAILED: $*" >&2; exit 1; }

echo "==> 1/6 unpacking the base backup"
rm -rf "${RESTORE_PGDATA}"; mkdir -p "${RESTORE_PGDATA}"
tar -xzf "${BASE_BACKUP}/base.tar.gz" -C "${RESTORE_PGDATA}" || fail "base.tar.gz did not unpack"
if [[ -f "${BASE_BACKUP}/pg_wal.tar.gz" ]]; then
  tar -xzf "${BASE_BACKUP}/pg_wal.tar.gz" -C "${RESTORE_PGDATA}/pg_wal"
fi

echo "==> 2/6 configuring recovery"
{
  echo "port = ${RESTORE_PORT}"
  echo "restore_command = 'cp ${WAL_ARCHIVE:-/var/backups/lacteva/wal}/%f %p'"
  if [[ -n "${TARGET_TIME}" ]]; then
    echo "recovery_target_time = '${TARGET_TIME}'"
    echo "recovery_target_action = 'promote'"
  fi
} >> "${RESTORE_PGDATA}/postgresql.auto.conf"
touch "${RESTORE_PGDATA}/recovery.signal"

echo "==> 3/6 starting the restored instance"
pg_ctl -D "${RESTORE_PGDATA}" -o "-p ${RESTORE_PORT}" -w -t 300 start \
  || fail "the restored instance did not start"
trap 'pg_ctl -D "${RESTORE_PGDATA}" -m immediate stop >/dev/null 2>&1 || true' EXIT

export LACTEVA_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASSWORD}@localhost:${RESTORE_PORT}/${PGDATABASE:-lacteva}"

echo "==> 4/6 schema is at head"
uv run alembic upgrade head || fail "migrations did not apply to the restored database"

echo "==> 5/6 business integrity (the platform's own rules, deep)"
uv run python -m platform_core.core.backup.cli integrity --deep \
  || fail "the restored data violates the platform's business rules"

echo "==> 6/6 smoke test: the application answers on the restored data"
uv run python - <<'PY' || fail "the application could not serve the restored data"
import asyncio, os
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
echo "  base backup : ${BASE_BACKUP}"
echo "  target time : ${TARGET_TIME:-<end of WAL>}"
echo "  verified    : schema, business integrity, projections, application readiness"
