#!/usr/bin/env bash
# Make a backup failure impossible to miss on THIS machine (DEMO-011 §8).
#
# Invoked by `OnFailure=lacteva-backup-alert@%n.service` from every backup
# unit. The work order asks for a lightweight mechanism using what already
# exists, and not an expensive monitoring platform — so this uses three things
# that are already here and cost nothing:
#
#   1. the JOURNAL, at error priority, where `journalctl -p err` finds it;
#   2. a MARKER FILE, so the state survives a reboot and a log rotation and
#      can be read by a human, a login banner, or the next deploy;
#   3. nothing else. `core/alerts.py` is a RULES engine driven by health
#      snapshots, not a command, so the right integration there was a rule
#      rather than a shell-out — DEMO-011 added `backups_stale` and
#      `backups_degraded` to it, which fire from the platform's own health
#      probe and reach Prometheus. This script covers what that probe cannot
#      see: the machine's own scheduled job failing.
#
# It must never fail. An alerting path that can itself fail turns one problem
# into silence, so every step is best-effort and the script always exits 0.
set -uo pipefail

UNIT="${1:-unknown.service}"
MARKER="${BACKUP_ALERT_MARKER:-/var/log/lacteva/BACKUP-FAILED}"
WHEN="$(date -u +%FT%TZ)"

# 1. The journal, at a priority that stands out.
logger -t lacteva-backup -p daemon.err \
  "BACKUP FAILURE: ${UNIT} failed at ${WHEN}. See DEMO-011-DR-RUNBOOK.md." 2>/dev/null || true

# 2. The marker. Appended, never truncated: three failures in a row is a
#    different situation from one, and an operator should be able to see that.
{
  printf '%s  %s FAILED\n' "${WHEN}" "${UNIT}"
  systemctl status "${UNIT}" --no-pager -n 15 2>/dev/null | sed 's/^/    /'
  printf '\n'
} >> "${MARKER}" 2>/dev/null || true

echo "${WHEN}  alerted for ${UNIT} (journal + ${MARKER})"
exit 0
