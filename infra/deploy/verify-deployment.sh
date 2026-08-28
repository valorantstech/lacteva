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

# AWS-001: the environment lives at /etc/lacteva/.env.production — where
# deploy.sh, INFRASTRUCTURE.md and the compose file's own `env_file:` all agree
# it lives. Defaulting to `.env.production` next to the compose file meant
# every compose call here died with "couldn't find env file", and the checks
# that depend on them reported the database down on a database that was up.
ENV_FILE="${ENV_FILE:-/etc/lacteva/.env.production}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file ${ENV_FILE}}"
# WO-37: default to the deployment's OWN name, not localhost.
#
# AWS-001 taught this script to follow nginx's 301 to HTTPS. The redirect
# lands on `https://localhost`, and the certificate is issued for the
# deployment's real hostname — so curl refused it:
#
#   SSL: no alternative certificate subject name matches target host 'localhost'
#
# and the verifier failed at its first gate on a platform that was serving
# perfectly. That is the same shape as the bug AWS-001 fixed, one layer down:
# a healthy deployment failing its own verification, which is what triggers
# deploy.sh's automatic rollback.
#
# `LACTEVA_PUBLIC_URL` is the name the certificate is for and is already in
# the environment file every other part of this script reads. Falling back to
# localhost keeps a first deployment — which has no DNS name yet — working.
PUBLIC_URL="$(sed -n 's/^LACTEVA_PUBLIC_URL=//p' "${ENV_FILE}" 2>/dev/null | tail -1 | tr -d '\042\047')"   # \042 = " and \047 = ', either may quote it
API="${API_URL:-${PUBLIC_URL:-http://localhost:${HTTP_PORT:-80}}}"

# AWS-001: FOLLOW the redirect.
#
# nginx answers plain HTTP with a 301 to HTTPS — correctly, and by design. The
# default `API` above is http://localhost, so every `curl -fsS` here was
# handed a 301 HTML body and `json.load` died on "Expecting value: line 1
# column 1". The verifier therefore failed on a stack that was serving
# perfectly, which then triggered deploy.sh's automatic rollback: a healthy
# deployment torn down by its own smoke test.
#
# `VERIFY_TLS=0` additionally accepts a self-signed certificate. It is opt-in
# and must stay that way — silently skipping certificate verification would
# make this script pass against a machine-in-the-middle.
CURL_OPTS=(--location --max-time 10)
[ "${VERIFY_TLS:-1}" = "0" ] && CURL_OPTS+=(--insecure)
TIMEOUT="${VERIFY_TIMEOUT:-120}"

pass() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
FAILURES=0

step "Waiting for the API to report ready (up to ${TIMEOUT}s)"
# Poll readiness rather than sleeping: readiness is the platform's own answer
# to "should I receive traffic", and it already aggregates every probe below.
#
# DEMO-013: wait for the SAMPLED payload, not merely for a 200.
#
# `/health/ready` has a deliberate startup window (`core/observability.py`):
# before the first health sample lands it answers 200 with the cheap adapter
# checks — `{"status": "ok", "checks": {"database": true}}` — so that a
# just-started instance is not reported unready for a whole sampling
# interval. That is correct for a load balancer and wrong for this script,
# which then asserts the four-level component vocabulary against booleans and
# reports every probe "not being probed at all".
#
# It cost a production deployment: the verifier failed a healthy stack, and
# the automatic rollback it triggered failed the same way one second later,
# leaving old code running against a new schema. `platform_status` appears
# only once a real sample exists, so that is what "ready" means here.
deadline=$(( $(date +%s) + TIMEOUT ))
sampled() {
  curl -fsS "${CURL_OPTS[@]}" "${API}/health/ready" 2>/dev/null \
    | python3 -c "import json,sys; sys.exit(0 if 'platform_status' in json.load(sys.stdin) else 1)" \
    2>/dev/null
}
until sampled; do
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    fail "API never reported a sampled health snapshot within ${TIMEOUT}s"
    echo "  last response:" >&2
    curl -sS --max-time 5 "${CURL_OPTS[@]}" "${API}/health/ready" >&2 || true
    exit 1
  fi
  sleep 2
done
pass "API is ready (health sampler has run)"

READY_JSON="$(curl -fsS "${CURL_OPTS[@]}" "${API}/health/ready")"

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
[ "${UNFORCED}" = "0" ] && pass "policies are FORCED (the owner does not bypass them)" \
  || fail "${UNFORCED} table(s) have RLS enabled but NOT forced — the owner bypasses them"

# VER-001 — the check whose absence made everything above cosmetic.
#
# Present + forced + covering is NOT enforcement. A SUPERUSER, and any role
# with BYPASSRLS, ignores row-level security entirely; FORCE covers the table
# OWNER and says nothing about superusers. The API used to connect as
# ${POSTGRES_USER}, which the official postgres image creates as a superuser,
# so every assertion above passed while not one policy was doing anything.
APP_ROLE="${LACTEVA_APP_USER:-lacteva_app}"
# AWS-001: `lacteva`, matching every other psql call in this file. This one
# line defaulted to `lacteva_owner`, a role no deployment creates, so the
# connection failed and the check errored out — and this is the check that
# catches the VER-001 defect, where the API connects as a superuser and every
# RLS policy is silently inert. A verification that cannot run is worse than
# one that is absent, because the script still printed green above it.
ROLE_STATE="$(${COMPOSE} exec -T postgres psql -U "${POSTGRES_USER:-lacteva}" -d "${POSTGRES_DB:-lacteva}" -tAc \
  "SELECT coalesce((SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname='${APP_ROLE}')::text, 'missing')" \
  2>/dev/null | tr -d '[:space:]')"
# AWS-001: `false`/`true`, not `f`/`t`. `f` and `t` are how psql DISPLAYS a
# boolean; an explicit `::text` cast — which the query above does — produces
# `false`/`true`. So this case never matched, and a correctly configured
# platform was told its application role did not exist. Both spellings are
# accepted now, because the query could reasonably be written either way and
# the cost of being wrong here is reporting RLS as enforced when it is inert.
case "${ROLE_STATE}" in
  f|false) pass "the API role ${APP_ROLE} is NOSUPERUSER/NOBYPASSRLS — policies are enforced" ;;
  t|true) fail "the API role ${APP_ROLE} is SUPERUSER or has BYPASSRLS — RLS is INERT and every tenant can be read by any request" ;;
  *) fail "the API role ${APP_ROLE} does not exist — infra/postgres/init/10-application-role.sh did not run (see DEPLOYMENT.md §Database roles)" ;;
esac

[ "${LACTEVA_APP_USER:-lacteva_app}" != "${POSTGRES_USER:-lacteva_owner}" ] \
  && pass "the API and the schema owner are different roles" \
  || fail "LACTEVA_APP_USER equals POSTGRES_USER — the API is running as the schema owner/superuser"

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
# AWS-001: `relay_pending_events` is the metric the platform actually exports
# (core/metrics.py). `lacteva_outbox_pending` exists nowhere in the codebase,
# so this check reported "the outbox depth is not being exported" on every
# deployment — and deploy.sh rolled back a healthy platform because of it.
# TLS-001: /metrics is restricted to private ranges on purpose, so running
# this script against the PUBLIC hostname gets a 403 — the guard working, not
# a fault. Detect that and say so, rather than failing the deployment or
# (worse) reporting the outbox as unexported.
METRICS_CODE="$(curl -s -o /dev/null -w '%{http_code}' "${CURL_OPTS[@]}" "${API}/metrics" || echo 000)"
if [ "${METRICS_CODE}" = "403" ]; then
  pass "outbox depth not checked — /metrics is restricted to internal ranges (run this from the host to include it)"
  LAG_1="" LAG_2="" SKIP_LAG=1
else
  LAG_1="$(curl -fsS "${CURL_OPTS[@]}" "${API}/metrics" | awk '/^relay_pending_events /{print $2}' | head -1)"
  sleep 5
  LAG_2="$(curl -fsS "${CURL_OPTS[@]}" "${API}/metrics" | awk '/^relay_pending_events /{print $2}' | head -1)"
fi
if [ "${SKIP_LAG:-0}" = "1" ]; then
  :
elif [ -z "${LAG_1}" ]; then
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
if curl -fsS "${CURL_OPTS[@]}" "${API}/nginx-health" >/dev/null 2>&1; then
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
