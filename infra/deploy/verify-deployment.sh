#!/usr/bin/env bash
# Post-deployment verification (DEP-001).
#
#   ./infra/deploy/verify-deployment.sh
#
# Runs after `docker compose up -d` and answers one question: is this
# deployment actually serving, or has it merely started?
#
# The distinction matters because the failure this catches is the quiet one.
# A container that is *up* with a dead consumer loop keeps answering every
# request perfectly while nothing downstream happens — no notification sent,
# no receipt generated, no projection updated. That is the most dangerous
# shape this platform has, and "docker compose ps" cannot see it.
#
# Every check is read-only. Nothing here writes business data; the smoke test
# (smoke-test.py) does that, deliberately, as a separate decision.
#
# Exit 0 = the deployment is serving. Non-zero = roll back (DEPLOYMENT.md §7).
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file .env.production}"
API="${API_URL:-http://localhost:${HTTP_PORT:-80}}"
TIMEOUT="${VERIFY_TIMEOUT:-120}"

pass() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
FAILURES=0

step "Waiting for the API to report ready (up to ${TIMEOUT}s)"
# Poll readiness rather than sleeping: readiness is the platform's own answer
# to "should I receive traffic", and it already aggregates every probe below.
deadline=$(( $(date +%s) + TIMEOUT ))
until curl -fsS --max-time 5 "${API}/health/ready" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    fail "API never became ready within ${TIMEOUT}s"
    echo "  last response:" >&2
    curl -sS --max-time 5 "${API}/health/ready" >&2 || true
    exit 1
  fi
  sleep 2
done
pass "API is ready"

READY_JSON="$(curl -fsS --max-time 10 "${API}/health/ready")"

step "Component health"
# The readiness payload carries every probe's status, so these are assertions
# about a document already fetched — not nine more round trips.
for component in database redis outbox consumers projections notifications jwt_keys background_workers; do
  status="$(printf '%s' "${READY_JSON}" | python3 -c "
import json,sys
print(json.load(sys.stdin).get('checks', {}).get('${component}', 'MISSING'))")"
  case "${status}" in
    healthy)  pass "${component}" ;;
    warning|degraded) pass "${component} (${status} — serving, but read the dashboard)" ;;
    MISSING)  fail "${component} is not being probed at all" ;;
    *)        fail "${component} is ${status}" ;;
  esac
done

step "Database"
if ${COMPOSE} exec -T postgres pg_isready -q; then
  pass "PostgreSQL accepting connections"
else
  fail "PostgreSQL is not accepting connections"
fi

# The schema must be at the revision this image expects. A deployment that
# started against an older schema is the failure that produces confusing
# errors hours later rather than a clean crash now.
DB_REV="$(${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER:-lacteva}" -d "${POSTGRES_DB:-lacteva}" \
  -tAc "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]' || true)"
CODE_REV="$(${COMPOSE} run --rm --no-deps -T api alembic heads 2>/dev/null \
  | awk '{print $1}' | tr -d '[:space:]' || true)"
if [ -n "${DB_REV}" ] && [ "${DB_REV}" = "${CODE_REV}" ]; then
  pass "schema at ${DB_REV} (matches the image)"
else
  fail "schema is at '${DB_REV}' but the image expects '${CODE_REV}'"
fi

step "Row-level security"
# SEC-002: every table that carries a tenant_id must have a policy, and
# `organization` — which IS the tenant — must have one too. Verifying this
# after deployment matters because RLS is enabled by MIGRATION: a database
# restored from an older backup, or one somebody rebuilt by hand, can be
# serving traffic with the policies simply absent.
UNCOVERED="$(${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER:-lacteva}" -d "${POSTGRES_DB:-lacteva}" -tAc "
  SELECT count(*) FROM information_schema.columns c
  WHERE c.table_schema='public' AND c.column_name='tenant_id'
    AND NOT EXISTS (SELECT 1 FROM pg_policies p
                    WHERE p.schemaname='public' AND p.tablename=c.table_name)" 2>/dev/null | tr -d '[:space:]')"
UNFORCED="$(${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER:-lacteva}" -d "${POSTGRES_DB:-lacteva}" -tAc \
  "SELECT count(*) FROM pg_class WHERE relrowsecurity AND NOT relforcerowsecurity" 2>/dev/null | tr -d '[:space:]')"
[ "${UNCOVERED}" = "0" ] && pass "every tenant-owned table has a policy" \
  || fail "${UNCOVERED} tenant-owned table(s) have NO RLS policy"
[ "${UNFORCED}" = "0" ] && pass "policies are FORCED (the app connects as the owner)" \
  || fail "${UNFORCED} table(s) have RLS enabled but NOT forced — the owner bypasses them"

step "Redis"
if ${COMPOSE} exec -T redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping' 2>/dev/null | grep -q PONG; then
  pass "Redis responding"
else
  fail "Redis is not responding — rate limiting will fail open"
fi

step "Background work"
# `background_workers` above says the loops are alive. This says they are
# making progress, which is a different question: a loop can be alive and
# stuck. Outbox lag that only grows is the signal.
LAG_1="$(curl -fsS --max-time 10 "${API}/metrics" | awk '/^lacteva_outbox_pending /{print $2}' | head -1)"
sleep 5
LAG_2="$(curl -fsS --max-time 10 "${API}/metrics" | awk '/^lacteva_outbox_pending /{print $2}' | head -1)"
if [ -z "${LAG_1}" ]; then
  fail "outbox depth is not being exported — cannot tell whether the relay is moving"
elif python3 -c "import sys; sys.exit(0 if float('${LAG_2}') <= float('${LAG_1}') or float('${LAG_2}') < 100 else 1)"; then
  pass "outbox is draining (${LAG_1} → ${LAG_2})"
else
  fail "outbox is growing (${LAG_1} → ${LAG_2}) — the relay is not keeping up"
fi

step "Projection registry"
PROJ="$(printf '%s' "${READY_JSON}" | python3 -c "
import json,sys
print(json.load(sys.stdin).get('checks', {}).get('projections', 'MISSING'))")"
[ "${PROJ}" = "healthy" ] && pass "projections healthy" || fail "projections: ${PROJ}"

step "Edge"
if curl -fsS --max-time 5 "${API}/nginx-health" >/dev/null 2>&1; then
  pass "nginx serving"
else
  fail "nginx is not answering its own health endpoint"
fi

printf '\n'
if [ "${FAILURES}" -eq 0 ]; then
  printf '\033[32mDEPLOYMENT VERIFIED — the platform is serving.\033[0m\n'
  printf 'Run ./infra/deploy/smoke-test.py next to prove the business path end to end.\n'
  exit 0
fi
printf '\033[31mDEPLOYMENT VERIFICATION FAILED (%s check(s)).\033[0m\n' "${FAILURES}" >&2
printf 'Roll back per DEPLOYMENT.md §7 before investigating — a half-serving\n' >&2
printf 'deployment is worse than the previous one.\n' >&2
exit 1
