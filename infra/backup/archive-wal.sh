#!/usr/bin/env bash
# Archive one WAL segment, atomically and idempotently (DEMO-011).
#
#   archive_command = '/opt/backup/archive-wal.sh %p %f'
#
# It replaces the archive_command PostgreSQL's own documentation suggests:
#
#   test ! -f /wal-archive/%f && cp %p /wal-archive/%f
#
# That line has a failure mode this deployment actually hit. `cp` is not
# atomic, so an interrupted copy leaves a PARTIAL file at the destination.
# `test ! -f` then sees a file, returns non-zero, and PostgreSQL retries the
# same segment forever. Archiving stops dead, `pg_wal` grows without bound on
# the database's own disk, and nothing alerts — PostgreSQL logs a warning and
# keeps serving, so the container stays healthy.
#
# Found on 2026-08-13: one truncated segment (3,342,336 of 16,777,216 bytes)
# written at 17:41 the previous day had blocked every segment since. 58 were
# queued in pg_wal, 945MB, still climbing, and point-in-time recovery had a
# silent eighteen-hour hole.
#
# THE RULES HERE
#
# 1. Write to a temporary file in the SAME directory, then `mv`. Rename within
#    one filesystem is atomic, so the destination name never exists in a
#    partial state. An interruption leaves a temp file, which is inert.
# 2. An identical file already present is SUCCESS. PostgreSQL may legitimately
#    re-archive a segment after a crash, and failing that would wedge the
#    archiver for the same reason the original did.
# 3. A DIFFERENT file under the same name is a hard failure. Same segment
#    name, different bytes means timelines have diverged or the archive is
#    corrupt, and silently overwriting it would destroy the recovery point.
#    Refusing is correct even though it stops archiving — that is a situation
#    a person has to look at.
# 4. fsync before the rename. A rename that survives a crash while the data
#    behind it does not is an archive full of empty promises.
set -euo pipefail

SOURCE="${1:?usage: archive-wal.sh <%p source path> <%f segment name>}"
SEGMENT="${2:?usage: archive-wal.sh <%p source path> <%f segment name>}"
ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/wal-archive}"
DEST="${ARCHIVE_DIR}/${SEGMENT}"

# PostgreSQL runs archive_command with the data directory as the working
# directory and passes %p relative to it, so this needs no path juggling.
[ -f "${SOURCE}" ] || { echo "archive-wal: source ${SOURCE} does not exist" >&2; exit 1; }
[ -d "${ARCHIVE_DIR}" ] || { echo "archive-wal: ${ARCHIVE_DIR} is not a directory" >&2; exit 1; }

if [ -f "${DEST}" ]; then
  if cmp -s "${SOURCE}" "${DEST}"; then
    exit 0   # rule 2: already archived, byte for byte. Nothing to do.
  fi
  # Rule 3.
  echo "archive-wal: ${SEGMENT} already exists with DIFFERENT content" >&2
  echo "archive-wal: refusing to overwrite a recovery point. Inspect:" >&2
  echo "archive-wal:   $(ls -l "${DEST}" 2>/dev/null)" >&2
  echo "archive-wal:   source is $(stat -c %s "${SOURCE}") bytes" >&2
  echo "archive-wal: if the archived copy is truncated, move it aside and" >&2
  echo "archive-wal: PostgreSQL will re-archive from pg_wal on the next retry." >&2
  exit 1
fi

TMP="$(mktemp "${ARCHIVE_DIR}/.${SEGMENT}.XXXXXX")"
# Any exit before the rename removes the temporary file, so a failed archive
# never leaves debris that a later run has to reason about.
trap 'rm -f "${TMP}"' EXIT

cp "${SOURCE}" "${TMP}"
# Rule 4. `sync` on the file, then on the directory entry the rename creates.
if command -v sync >/dev/null 2>&1; then
  sync "${TMP}" 2>/dev/null || sync
fi
chmod 0600 "${TMP}"
mv "${TMP}" "${DEST}"
trap - EXIT
if command -v sync >/dev/null 2>&1; then
  sync "${ARCHIVE_DIR}" 2>/dev/null || true
fi
exit 0
