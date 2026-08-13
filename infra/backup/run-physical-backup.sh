#!/usr/bin/env bash
# Weekly physical backup, run where PostgreSQL is actually reachable (DEMO-011).
#
# `pg-backup.sh` does the work: `pg_basebackup`, `pg_verifybackup`, base
# retention, and WAL archive pruning against the oldest retained base. This
# wrapper exists only to run it in the right place.
#
# The weekly timer used to invoke `pg-backup.sh` directly on the host, where it
# failed on its first line with `PGHOST: set PGHOST` — and would have failed on
# the next line too, because the database port is DELIBERATELY not published
# (docker-compose.production.yml: "reaching the database means being on this
# network or opening an SSH tunnel"). A base backup taken from the host could
# never have connected. The unit had never run, so nobody found out.
#
# So it runs inside the `postgres` container, which is the only place that has
# all four things it needs: the client tools, network reach to the server, the
# WAL archive, and — since DEMO-011 — the backup directory.
set -euo pipefail

COMPOSE="${COMPOSE:-docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production}"
RETENTION_DAYS="${BASE_RETENTION_DAYS:-35}"

log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }

log "starting physical base backup"

# `exec` rather than `run`: the running server already has everything mounted,
# and a fresh container would need the same mounts declared twice.
# --user postgres, not root (DEMO-011 §9). `compose exec` runs as root by
# default, which left every base backup file root-owned inside a directory
# owned by uid 999 — inconsistent with the rest of the backup tree and more
# privilege than taking a backup needs. The server itself runs as 999.
if ! ${COMPOSE} exec -T --user postgres \
  -e PGHOST=localhost \
  -e PGUSER="${POSTGRES_USER:?set POSTGRES_USER}" \
  -e PGPASSWORD="${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}" \
  -e PGDATABASE="${POSTGRES_DB:-lacteva}" \
  -e BACKUP_ROOT=/backup \
  -e WAL_ARCHIVE=/wal-archive \
  -e RETENTION_DAYS="${RETENTION_DAYS}" \
  postgres /opt/backup/pg-backup.sh; then
  log "FAILED: physical backup did not complete"
  exit 1
fi

# Report against the HOST's view, because that is the disk an operator has to
# manage. `df` inside the container reports the same device by a different
# name, which is more confusing than helpful in a log someone reads at 3am.
HOST_DIR="${LACTEVA_BACKUP_DIR:-/var/lib/lacteva/backup}/base"
if [ -d "${HOST_DIR}" ]; then
  COUNT="$(find "${HOST_DIR}" -mindepth 1 -maxdepth 1 -type d | wc -l)"
  # The same guard the logical backup has: retention must never take the last
  # recovery point, and if it has, that is a failure rather than a tidy log.
  if [ "${COUNT}" -lt 1 ]; then
    log "FAILED: no base backup remains after retention. This should be impossible."
    exit 1
  fi
  log "done: ${COUNT} base backup(s) retained. Volume: $(df -h "${HOST_DIR}" | awk 'NR==2 {print $5" used, "$4" free"}')"
else
  log "done (host view of ${HOST_DIR} unavailable; ran inside the container)"
fi
