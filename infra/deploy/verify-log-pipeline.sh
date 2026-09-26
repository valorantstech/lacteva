#!/usr/bin/env bash
# WO-101 / WO-102 — the log store has RECEIVED something, or the deploy fails.
#
# promtail, Loki and Grafana all reported "Up (healthy)" on production while
# Loki held nothing, so a health probe is not enough: this makes one request to
# the API with its own X-Request-ID and insists on finding it in Loki.
#
# It WAITS. The first version fired seconds after promtail was recreated, saw
# a counter at zero, failed, and rolled a good deploy back — a minute later the
# rollback's own run saw 142 lines. A freshly started promtail needs its first
# discovery refresh (15 s) and its first batch; this polls for up to
# LOG_PIPELINE_TIMEOUT seconds (default 90) and says how long it waited.
#
#   COMPOSE="docker compose -f … --env-file …" ./verify-log-pipeline.sh
#   exit 0: shipped and queryable; exit 1: not within the timeout.
set -uo pipefail

COMPOSE="${COMPOSE:?set COMPOSE to the compose command for this stack}"
TIMEOUT="${LOG_PIPELINE_TIMEOUT:-90}"
POLL="${LOG_PIPELINE_POLL:-5}"

pass() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; }

started="$(date +%s)"
waited() { echo $(( $(date +%s) - started )); }

# The probe: straight at the api container, so the id is the one the api
# binds and logs (`core/observability.py` honours X-Request-ID).
PROBE="verify-$(date -u +%Y%m%dT%H%M%SZ)-$$"
${COMPOSE} exec -T api python -c "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/health/live', headers={'X-Request-ID': '${PROBE}'}), timeout=5)" >/dev/null 2>&1 || true

sent="0"
found="0"
while :; do
  sent="$(${COMPOSE} exec -T promtail wget -qO- http://127.0.0.1:9080/metrics 2>/dev/null | sed -n 's/^promtail_sent_entries_total{[^}]*} //p' | head -1)"
  sent="${sent:-0}"
  if [ "${sent}" != "0" ]; then
    since="$(( $(date +%s) - 300 ))000000000"
    found="$(${COMPOSE} exec -T loki wget -qO- "http://127.0.0.1:3100/loki/api/v1/query_range?query=%7Bservice%3D%22api%22%7D%20%7C%3D%20%22${PROBE}%22&limit=1&start=${since}" 2>/dev/null | grep -c "${PROBE}" || true)"
    found="${found:-0}"
    [ "${found}" != "0" ] && break
  fi
  if [ "$(waited)" -ge "${TIMEOUT}" ]; then break; fi
  sleep "${POLL}"
done

if [ "${sent}" = "0" ]; then
  fail "promtail has shipped NOTHING to Loki after waiting $(waited)s (promtail_sent_entries_total=0) — check 'docker compose logs promtail' for discovery errors"
  exit 1
fi
pass "promtail has shipped ${sent} lines to Loki (after $(waited)s)"
if [ "${found}" = "0" ]; then
  fail "a request made $(waited)s ago cannot be found in Loki by its request_id (${PROBE}) — the log pipeline delivers nothing queryable"
  exit 1
fi
pass "a request made now is queryable in Loki by its request_id (${PROBE}, after $(waited)s)"
