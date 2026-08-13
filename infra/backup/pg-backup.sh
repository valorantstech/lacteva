#!/usr/bin/env bash
# PostgreSQL physical backup (BAK-001).
#
# The production first line: a base backup plus continuous WAL archiving,
# which together give point-in-time recovery. The platform's own logical
# backup (`python -m platform_core.core.backup.cli backup`) is the verifiable
# second line — see BACKUP.md for why both exist.
#
# This script does NOT verify the backup. Verification requires restoring it,
# which is what pg-restore-test.sh does, and a backup nobody has restored is
# not evidence of anything.
set -euo pipefail

: "${PGHOST:?set PGHOST}"
: "${PGUSER:?set PGUSER}"
: "${BACKUP_ROOT:?set BACKUP_ROOT (e.g. /var/backups/lacteva)}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_ROOT}/base/${STAMP}"
mkdir -p "${TARGET}"

# DEMO-011: a failed run must not leave a directory behind.
#
# Two aborted attempts left three-file directories in `base/` that looked
# exactly like recovery points in a listing, and `pg_archivecleanup` then
# prunes WAL against the OLDEST of them. A backup that failed is not a
# recovery point and must not be mistaken for one at 3am. The trap is cleared
# on the success path at the end of the script.
cleanup_failed() {
  echo "FAILED: removing the incomplete backup at ${TARGET}" >&2
  rm -rf "${TARGET}" "${TARGET}.manifest.sha256"
}
trap cleanup_failed EXIT

echo "==> base backup -> ${TARGET}"
# -X stream: ship the WAL generated DURING the backup with it, so the base is
# self-consistent without depending on the archive having caught up.
# -C -c fast: checkpoint immediately rather than waiting, so the window in
# which the backup lags the database is as small as possible.
# DEMO-011: PLAIN, not `--format=tar --gzip`.
#
# `pg_verifybackup` on PostgreSQL 16 reads a plain data directory. Pointed at
# a tar-format backup it reports every single file as "present in the manifest
# but not on disk" and then fails on `pg_waldump: could not open directory
# .../pg_wal`. So the script's own verification step could never have passed —
# the two lines contradicted each other, and nobody found out because the
# weekly unit had never run at all.
#
# Tar verification arrived in PostgreSQL 17. Until this deployment is on 17,
# the choice is a verifiable backup or a compressed one, and an unverified
# backup is not a backup. Plain also restores faster, which is what the base
# backup is FOR — the logical backup is the compact line of defence at 17MB.
#
# Cost: roughly the size of the data directory per weekly backup (~950MB
# today), bounded by the 35-day retention below, on a 49GB volume.
pg_basebackup \
  --pgdata="${TARGET}" \
  --format=plain \
  --wal-method=stream \
  --checkpoint=fast \
  --progress --verbose

echo "==> verifying the base backup against its own manifest"
# PITR-001: `pg_basebackup` exiting zero says the files were copied, not that
# they are internally consistent. `pg_verifybackup` checks every file against
# the manifest checksums, and it costs seconds. A base backup nobody verified
# is discovered to be bad during a recovery.
pg_verifybackup "${TARGET}" || {
  echo "FAILED: pg_verifybackup rejected ${TARGET} — this backup is not usable" >&2
  exit 1
}

echo "==> recording the manifest checksum"
# pg_basebackup writes backup_manifest with per-file checksums; keep a digest
# of it so tampering with both file and manifest is detectable.
#
# DEMO-011: the digest goes BESIDE the backup, not inside it. Written into the
# directory it made every later `pg_verifybackup` report
#
#   "backup_manifest.sha256" is present on disk but not in the manifest
#
# on a backup that was perfectly good — because a base backup directory must
# contain exactly what the manifest lists and nothing else. The weekly restore
# check and any operator re-verifying by hand would both have seen an error
# and had to decide whether to believe it.
sha256sum "${TARGET}/backup_manifest" > "${TARGET}.manifest.sha256" 2>/dev/null || true

echo "==> pruning base backups older than ${RETENTION_DAYS:-35} days"
# PITR-001: `-mindepth 1` is load-bearing. Without it, `find DIR -maxdepth 1
# -type d` matches DIR ITSELF, so `rm -rf` deletes the whole base/ directory —
# every backup, including today's. It only fires once base/ is itself older
# than the window, which happens exactly when backups have stopped: the moment
# you most need the old ones.
find "${BACKUP_ROOT}/base" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS:-35}" \
  -exec rm -rf {} + 2>/dev/null || true

# --- WAL archive pruning ----------------------------------------------------
# PITR-001. Base backups without their WAL are snapshots, not point-in-time
# recovery; WAL without a base backup is unusable. So the archive is pruned
# against the OLDEST base backup still retained — never against a date.
#
# `pg_archivecleanup` removes segments older than the one named, which is the
# only safe rule: anything newer may be needed to roll that base forward.
if [ -n "${WAL_ARCHIVE:-}" ] && [ -d "${WAL_ARCHIVE}" ]; then
  OLDEST="$(find "${BACKUP_ROOT}/base" -mindepth 1 -maxdepth 1 -type d | sort | head -1)"
  if [ -n "${OLDEST}" ]; then
    # The .backup label written into the archive names the first segment that
    # base backup needs. Cleaning to it keeps every retained base restorable.
    START_SEG="$(find "${WAL_ARCHIVE}" -name '*.backup' -printf '%f\n' 2>/dev/null \
      | sort | head -1 | cut -d. -f1)"
    if [ -n "${START_SEG}" ]; then
      echo "==> pruning WAL older than ${START_SEG} (needed by ${OLDEST})"
      pg_archivecleanup "${WAL_ARCHIVE}" "${START_SEG}" || true
    else
      echo "==> WAL archive NOT pruned: no .backup label found."
      echo "    Refusing to guess — deleting a segment a base backup needs"
      echo "    silently turns that backup into an unrestorable directory."
    fi
  fi
else
  echo "==> WAL_ARCHIVE not set; skipping archive pruning"
  echo "    NOTE: without a WAL archive there is NO point-in-time recovery."
fi

trap - EXIT   # from here the backup exists and is verified; keep it.
echo "==> done: ${TARGET}"
echo "REMINDER: this backup is unverified until pg-restore-test.sh has restored it."
