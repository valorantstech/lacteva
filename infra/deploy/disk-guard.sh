#!/usr/bin/env bash
# Keep Docker from silently eating the host disk (DEMO-010).
#
# The disk reached 100% twice during DEMO-009. Nothing dramatic caused it:
# build cache, superseded image layers and old release directories accumulate
# a little on every deploy and nothing ever removed them. A full disk stops
# PostgreSQL from writing, which is the worst failure this platform has.
#
# So this runs on a timer and reclaims in a deliberate order — cheapest and
# most obviously safe first, stopping as soon as the disk is comfortable
# again. It is a guard, not a scheduled `docker system prune -a`: that would
# delete the previous release's image, and the previous release's image is
# exactly what `deploy.sh --rollback` needs at 3am.
#
#   ./disk-guard.sh              # reclaim only if above the high-water mark
#   ./disk-guard.sh --force      # reclaim now, whatever the usage
#   ./disk-guard.sh --report     # say what would be reclaimed, change nothing
#
# Exit codes: 0 fine (or reclaimed to below the mark), 1 still above the mark
# after everything safe was tried — which is a real alert, not a cleanup job.
set -euo pipefail

# Start reclaiming here. 75% on a 38GB disk leaves ~9GB, which is more than a
# full backup plus a release plus the room PostgreSQL wants for a checkpoint.
HIGH_WATER="${DISK_HIGH_WATER:-75}"
# Stop reclaiming here rather than at zero: churning the cache to nothing just
# makes the next build slow for no benefit.
TARGET="${DISK_TARGET:-60}"
# Below this, refuse to declare success. A guard that reports OK on a disk
# that is about to stop PostgreSQL is worse than no guard.
CRITICAL="${DISK_CRITICAL:-90}"
RELEASES="${RELEASES_DIR:-/opt/lacteva/releases}"
KEEP_RELEASES="${KEEP_RELEASES:-3}"
LOG="${DISK_GUARD_LOG:-/var/log/lacteva/disk-guard.log}"

MODE="check"
[ "${1:-}" = "--force" ] && MODE="force"
[ "${1:-}" = "--report" ] && MODE="report"

# STDOUT ONLY. The systemd unit already redirects stdout to ${LOG}
# (`StandardOutput=append:`), so writing there as well printed every line
# twice — which is how the first scheduled run appeared in the log.
log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }

usage() { df --output=pcent / | tail -1 | tr -dc '0-9'; }

# Everything below the high-water mark is left alone, so the ordinary state of
# this timer is to do nothing at all and say so.
reclaim_if_needed() {
  local step="$1" cmd="$2" before after
  before="$(usage)"
  if [ "${before}" -le "${TARGET}" ]; then
    log "  ${step}: skipped, already at ${before}% (target ${TARGET}%)"
    return
  fi
  log "  ${step}: running at ${before}%"
  eval "${cmd}" >/dev/null 2>&1 || log "  ${step}: FAILED (continuing — the next step may still help)"
  after="$(usage)"
  log "  ${step}: ${before}% → ${after}%"
}

# --- old releases ----------------------------------------------------------
# Keep the current one, the one to roll back to, and one more. Never touch the
# symlinked current release even if it sorts oldest.
prune_releases() {
  local current keep
  [ -d "${RELEASES}" ] || return 0
  current="$(readlink -f "${CURRENT_LINK:-/opt/lacteva/current}" 2>/dev/null || true)"
  keep="${KEEP_RELEASES}"
  # shellcheck disable=SC2012  # release directories are timestamp-named
  ls -1dt "${RELEASES}"/*/ 2>/dev/null | tail -n "+$((keep + 1))" | while read -r dir; do
    if [ "$(readlink -f "${dir}")" = "${current}" ]; then
      log "    keeping ${dir} — it is the current release"
      continue
    fi
    log "    removing ${dir}"
    rm -rf "${dir}"
  done
}

start="$(usage)"
log "disk guard: / at ${start}% (high water ${HIGH_WATER}%, target ${TARGET}%, mode ${MODE})"

if [ "${MODE}" = "report" ]; then
  docker system df 2>/dev/null || true
  echo "releases:"
  ls -1dt "${RELEASES}"/*/ 2>/dev/null | tail -n "+$((KEEP_RELEASES + 1))" || echo "  none to remove"
  exit 0
fi

if [ "${MODE}" = "check" ] && [ "${start}" -lt "${HIGH_WATER}" ]; then
  log "nothing to do"
  exit 0
fi

# Order matters. Build cache is pure recomputable waste and is the largest
# single consumer here — 3GB of it when this script was written. Dangling
# images are layers no tag points at. Only then do we touch tagged images, and
# even then only ones older than a week, because `--rollback` needs the
# previous release's image to still exist.
reclaim_if_needed "build cache"      "docker builder prune --force --all"
reclaim_if_needed "dangling images"  "docker image prune --force"
reclaim_if_needed "stopped containers" "docker container prune --force"
reclaim_if_needed "old release directories" "prune_releases"
reclaim_if_needed "images older than 7 days" "docker image prune --force --all --filter until=168h"
reclaim_if_needed "journal over 200M"  "journalctl --vacuum-size=200M"

end="$(usage)"
log "disk guard: / at ${end}% (was ${start}%)"

if [ "${end}" -ge "${CRITICAL}" ]; then
  log "STILL AT ${end}% AFTER RECLAIMING EVERYTHING SAFE — this needs a person"
  exit 1
fi
exit 0
