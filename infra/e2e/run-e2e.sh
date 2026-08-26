#!/usr/bin/env bash
# Real client↔server E2E harness (P1-E2E-HARNESS-001).
#
# One command, one process tree, no leftovers: a fresh database, the REAL
# FastAPI application served by uvicorn, a local mail sink so the real
# invitation path can deliver a real token, a synthetic dairy seeded through
# the platform's OWN HTTP API, then the client suites driven against that
# server. Everything is torn down on exit, success or failure.
#
#   ./infra/e2e/run-e2e.sh            # everything
#   ./infra/e2e/run-e2e.sh mobile     # just the Flutter client suite
#   ./infra/e2e/run-e2e.sh portal     # just the portal client suite
#   ./infra/e2e/run-e2e.sh seed-only  # stand it up and leave it running
#
# No Docker, no external services, no credentials: the whole world is created
# from nothing each run, which is what makes it repeatable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CORE="$ROOT/services/platform-core"
WORK="${LACTEVA_E2E_WORK:-$(mktemp -d -t lacteva-e2e-XXXXXX)}"
API_PORT="${LACTEVA_E2E_PORT:-8099}"
SMTP_PORT="${LACTEVA_E2E_SMTP_PORT:-8025}"
API="http://127.0.0.1:${API_PORT}"
WHAT="${1:-all}"

PY="$CORE/.venv/bin/python"
[ -x "$PY" ] || { echo "FATAL: $PY missing — see CLAUDE.md (uv is not installed locally)"; exit 2; }

mkdir -p "$WORK/mail"
echo "e2e workspace: $WORK"

export LACTEVA_ENV=dev

# --- the database ------------------------------------------------------------
# REAL PostgreSQL, from the `pgserver` wheel, exactly as the verification
# proofs do it (no Docker, no daemon, no root). SQLite is not an option here
# for two reasons the harness exists to respect: row-level security is a
# PostgreSQL feature, so an RLS assertion on SQLite would be theatre; and a
# real server runs five background workers whose concurrent writes SQLite's
# single-writer lock cannot serve (it raises StaleDataError under load).
echo "── starting a real PostgreSQL (pgserver wheel) ──"
eval "$("$PY" "$ROOT/infra/ci/local_postgres.py" --print-env)"
export PGUSER="${PGUSER:-postgres}"
E2E_DB="lacteva_e2e_$$"
createdb "$E2E_DB"
export LACTEVA_DATABASE_URL="postgresql+asyncpg://$PGUSER@/$E2E_DB?host=$PGHOST"
echo "   database $E2E_DB on $PGHOST"
export LACTEVA_EVENT_BUS=memory
# The PRODUCTION dispatch mode, deliberately. `inline` is the unit suite's
# mode and is refused in prod; combined with the relay workers a real server
# starts, it races them (StaleDataError on event_outbox). The harness exists to
# run what production runs.
export LACTEVA_OUTBOX_MODE=background
export LACTEVA_JWT_SECRET=e2e-secret-0123456789abcdef0123456789abcdef
export LACTEVA_RATE_LIMIT_BACKEND=memory
# Rate limiting is REAL and stays real in every other environment; the harness
# turns it off for one reason, recorded rather than hidden: seeding plus the
# suite's own logins exceed the login rule (10/minute per IP), and a test that
# fails because the platform correctly defended itself teaches nothing. The
# limiter's behaviour is proven by the backend suite — and this harness
# observed it enforcing at the real boundary before this line was added.
export LACTEVA_RATE_LIMIT_ENABLED=false
# A refusal in this harness is always interesting, so the platform records what
# its transaction actually had bound when it refused (off everywhere else). This
# is what turned "a just-created row is not found" from a rumour into a cause.
export LACTEVA_SESSION_DIAGNOSTICS="${LACTEVA_SESSION_DIAGNOSTICS:-true}"
# The real invitation path: the platform will not hand a raw token back through
# the API (SEC-003/F-04), so the harness receives it by real SMTP delivery.
export LACTEVA_NOTIFICATION_EMAIL_PROVIDER=smtp
export LACTEVA_SMTP_HOST=127.0.0.1
export LACTEVA_SMTP_PORT="$SMTP_PORT"
export LACTEVA_SMTP_SECURITY=none
export LACTEVA_SMTP_FROM_ADDRESS=e2e@lacteva.example
export LACTEVA_MESSAGING_MODE=sandbox
export LACTEVA_E2E_API="$API"

PIDS=()
cleanup() {
  local rc=$?
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  if [ -n "${E2E_DB:-}" ] && [ "${LACTEVA_E2E_KEEP:-0}" != "1" ]; then
    dropdb --if-exists "$E2E_DB" > /dev/null 2>&1 || true
  fi
  if [ "${LACTEVA_E2E_KEEP:-0}" = "1" ]; then
    echo "kept workspace: $WORK"
  else
    rm -rf "$WORK"
  fi
  exit $rc
}
trap cleanup EXIT INT TERM

wait_for() { # url, seconds
  local url="$1" limit="${2:-40}" i=0
  until curl -sf -o /dev/null "$url"; do
    i=$((i + 1))
    [ "$i" -ge "$limit" ] && { echo "FATAL: $url did not come up"; tail -30 "$WORK/server.log" 2>/dev/null; return 1; }
    sleep 0.5
  done
}

echo "── migrating a fresh database ──"
(cd "$CORE" && "$CORE/.venv/bin/alembic" upgrade head > "$WORK/alembic.log" 2>&1) \
  || { echo "FATAL: migrations failed"; tail -20 "$WORK/alembic.log"; exit 1; }

echo "── starting the mail sink ──"
"$PY" "$ROOT/infra/e2e/mailsink.py" "$SMTP_PORT" "$WORK/mail" > "$WORK/mailsink.log" 2>&1 &
PIDS+=($!)

echo "── starting the real platform ──"
(cd "$CORE" && "$CORE/.venv/bin/uvicorn" platform_core.main:create_app --factory \
  --host 127.0.0.1 --port "$API_PORT" --log-level warning) > "$WORK/server.log" 2>&1 &
PIDS+=($!)
wait_for "$API/health/ready"
echo "   platform ready on $API"

echo "── seeding the synthetic dairy through the real API ──"
(cd "$CORE" && PYTHONPATH="$CORE/src" LACTEVA_E2E_MAIL="$WORK/mail" \
  "$PY" "$ROOT/infra/e2e/seed.py" "$WORK/fixture.json") \
  || { echo "FATAL: seeding failed"; exit 1; }

export LACTEVA_E2E_FIXTURE="$WORK/fixture.json"

if [ "$WHAT" = "seed-only" ]; then
  echo "── seeded; leaving the platform running (Ctrl-C to stop) ──"
  echo "   fixture: $WORK/fixture.json"
  LACTEVA_E2E_KEEP=1
  wait "${PIDS[1]}"
  exit 0
fi

FAILED=0

if [ "$WHAT" = "probe" ]; then
  # Ad-hoc investigation against the live, seeded platform.
  # shellcheck disable=SC2086 — the args are deliberately word-split
  "$PY" "${LACTEVA_E2E_PROBE:?set LACTEVA_E2E_PROBE to a script}" ${LACTEVA_E2E_PROBE_ARGS:-} || FAILED=1
  exit "$FAILED"
fi

if [ "$WHAT" = "all" ] || [ "$WHAT" = "mobile" ]; then
  echo "── mobile client → real API ──"
  if command -v flutter > /dev/null 2>&1; then
    (cd "$ROOT/apps/mobile" && flutter test test_e2e \
      --dart-define=LACTEVA_API_URL="$API" \
      --dart-define=LACTEVA_E2E_FIXTURE="$WORK/fixture.json") || FAILED=1
  else
    echo "   SKIPPED — flutter not on PATH"
  fi
fi

if [ "$WHAT" = "all" ] || [ "$WHAT" = "portal" ]; then
  echo "── portal client → real API ──"
  # LACTEVA_E2E_MAIL: the invite->accept journey has to read the token out of
  # the message the platform really delivered, exactly as `seed.py` does — the
  # API will not hand it back (SEC-003). Same sink, now visible to the portal
  # suite too (LACTEVA-ADMIN-002).
  (cd "$ROOT/apps/admin-portal" && LACTEVA_E2E_API="$API" \
    LACTEVA_E2E_FIXTURE="$WORK/fixture.json" \
    LACTEVA_E2E_MAIL="$WORK/mail" \
    npx vitest run --config vitest.e2e.config.ts) || FAILED=1
fi

[ "$FAILED" = "0" ] && echo "── E2E GREEN ──" || echo "── E2E FAILED ──"
exit "$FAILED"
