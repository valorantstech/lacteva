#!/usr/bin/env bash
# Is this platform actually protected right now? (DEMO-011 §8)
#
# There are two ways backups stop, and they need different detection.
#
#   1. A run FAILS. systemd sees a non-zero exit and `OnFailure=` fires.
#   2. A run never HAPPENS. Nothing fails, because nothing ran. systemd is
#      perfectly happy. Every dashboard is green.
#
# The second is what actually happened here: the backup units existed in the
# repository, referenced a `lacteva.service` that had never been installed,
# and were themselves never installed either. The only backups on the machine
# were incidental — taken by `deploy.sh` before an upgrade — and the platform's
# own health probe reported "healthy: verified backup 12.8 hours old" because
# somebody happened to have deployed the previous evening. A backup that only
# exists when a human deploys is not a backup schedule.
#
# So this asks the question from the outside: how old is the newest recovery
# point, and did the last attempt succeed? It answers from TWO independent
# sources, because they fail independently:
#
#   * the platform's own `backup.cli status`, which knows whether the backup
#     was verified — but needs the API to be up, and the API being down is a
#     perfectly good reason for backups to have stopped;
#   * the filesystem, which does not care whether anything is running.
#
# Exit 0 protected, 1 not. Non-zero makes systemd record a failure, which
# fires `OnFailure=lacteva-backup-alert.service`.
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production}"
BACKUP_HOST_DIR="${BACKUP_HOST_DIR:-${LACTEVA_BACKUP_DIR:-/var/lib/lacteva/backup}/logical}"
BASE_HOST_DIR="${BASE_HOST_DIR:-${LACTEVA_BACKUP_DIR:-/var/lib/lacteva/backup}/base}"
# 26h matches the platform's own `stale_after_hours`, so the two agree rather
# than arguing. A nightly backup at 02:15 is 26 hours old at 04:15 the day
# after it should have been replaced — comfortably one missed run, never two.
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"
BASE_MAX_AGE_HOURS="${BASE_MAX_AGE_HOURS:-192}"   # weekly + one missed run
STATE="${BACKUP_STATE_FILE:-/var/log/lacteva/backup-status}"

problems=()
note() { printf '%s\n' "$*"; }

age_hours_of_newest() {
  local dir="$1" newest
  [ -d "${dir}" ] || { echo "-1"; return; }
  newest="$(find "${dir}" -mindepth 1 -maxdepth 1 -type d -printf '%T@\n' 2>/dev/null | sort -rn | head -1)"
  [ -n "${newest}" ] || { echo "-1"; return; }
  echo $(( ( $(date +%s) - ${newest%.*} ) / 3600 ))
}

note "=== Lacteva backup watchdog — $(date -u +%FT%TZ) ==="

# --- 1. the filesystem, which is always available ----------------------------
LOGICAL_AGE="$(age_hours_of_newest "${BACKUP_HOST_DIR}")"
BASE_AGE="$(age_hours_of_newest "${BASE_HOST_DIR}")"
LOGICAL_COUNT="$(find "${BACKUP_HOST_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
BASE_COUNT="$(find "${BASE_HOST_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"

if [ "${LOGICAL_AGE}" -lt 0 ]; then
  problems+=("there is NO logical backup at ${BACKUP_HOST_DIR}")
elif [ "${LOGICAL_AGE}" -gt "${MAX_AGE_HOURS}" ]; then
  problems+=("the newest logical backup is ${LOGICAL_AGE}h old (limit ${MAX_AGE_HOURS}h)")
fi
note "logical backups: ${LOGICAL_COUNT}, newest ${LOGICAL_AGE}h old"

if [ "${BASE_AGE}" -lt 0 ]; then
  problems+=("there is NO physical base backup at ${BASE_HOST_DIR} — no point-in-time recovery")
elif [ "${BASE_AGE}" -gt "${BASE_MAX_AGE_HOURS}" ]; then
  problems+=("the newest base backup is ${BASE_AGE}h old (limit ${BASE_MAX_AGE_HOURS}h)")
fi
note "base backups:    ${BASE_COUNT}, newest ${BASE_AGE}h old"

# --- 2. the timers themselves ------------------------------------------------
# A disabled timer is the failure this whole script exists because of.
for unit in lacteva-backup-nightly.timer lacteva-backup-verify.timer lacteva-backup-weekly.timer; do
  if ! systemctl is-enabled "${unit}" >/dev/null 2>&1; then
    problems+=("${unit} is NOT enabled — it will not run after a reboot")
  elif ! systemctl is-active "${unit}" >/dev/null 2>&1; then
    problems+=("${unit} is enabled but NOT active — it is not scheduled now")
  fi
done
note "timers:          $(systemctl list-timers --no-pager lacteva-backup-\* 2>/dev/null | grep -c lacteva-backup || echo 0) scheduled"

# --- 3. what the last runs did ----------------------------------------------
for unit in lacteva-backup-nightly.service lacteva-backup-weekly.service lacteva-backup-verify.service; do
  result="$(systemctl show "${unit}" -p Result --value 2>/dev/null || echo unknown)"
  [ "${result}" = "success" ] || [ -z "${result}" ] \
    || problems+=("${unit} last finished with result=${result}")
done

# --- 4. the platform's own opinion ------------------------------------------
# It knows something the filesystem cannot: whether the backup VERIFIED.
if STATUS_JSON="$(${COMPOSE} exec -T api python -m platform_core.core.backup.cli status 2>/dev/null | sed -n '/^{/,$p')"; then
  HEALTHY="$(printf '%s' "${STATUS_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("healthy"))' 2>/dev/null || echo unknown)"
  DETAIL="$(printf '%s' "${STATUS_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("detail",""))' 2>/dev/null || echo '')"
  note "platform says:   healthy=${HEALTHY} (${DETAIL})"
  [ "${HEALTHY}" = "True" ] || problems+=("the platform reports it is not protected: ${DETAIL}")
else
  # Not fatal on its own — the filesystem checks above still stand — but an
  # API that cannot answer is itself worth saying out loud.
  note "platform says:   UNAVAILABLE (the API did not answer)"
  problems+=("could not ask the platform for backup status — is the API up?")
fi

# --- 5. one place an operator can look --------------------------------------
{
  printf 'checked_at=%s\n' "$(date -u +%FT%TZ)"
  printf 'logical_count=%s\nlogical_age_hours=%s\n' "${LOGICAL_COUNT}" "${LOGICAL_AGE}"
  printf 'base_count=%s\nbase_age_hours=%s\n' "${BASE_COUNT}" "${BASE_AGE}"
  printf 'protected=%s\n' "$([ ${#problems[@]} -eq 0 ] && echo yes || echo NO)"
  for p in ${problems[@]+"${problems[@]}"}; do printf 'problem=%s\n' "${p}"; done
} > "${STATE}.tmp" && mv "${STATE}.tmp" "${STATE}"

if [ ${#problems[@]} -eq 0 ]; then
  note "PROTECTED"
  exit 0
fi

note ""
note "NOT PROTECTED — ${#problems[@]} problem(s):"
for p in "${problems[@]}"; do note "  - ${p}"; done
note ""
note "Runbook: /opt/lacteva/current/DEMO-011-DR-RUNBOOK.md"
exit 1
