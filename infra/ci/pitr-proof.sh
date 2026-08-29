#!/usr/bin/env bash
# Point-in-Time Recovery proof (PITR-001).
#
#     ./infra/ci/pitr-proof.sh
#
# The physical recovery path, executed. This is the line of defence an
# operator reaches for FIRST in a real incident — "restore to 14:32, just
# before the bad deploy" — and until PITR-001 it had never been run. BAK-001
# scripted it, CI wired it, DR-001 recorded it as the largest untested
# guarantee on the platform.
#
# What this proves, in order:
#
#    1. A cluster configured for archiving actually archives
#    2. A realistic dairy exists before the base backup
#    3. `pg_basebackup` produces a verifiable base
#    4. Transactions continue AFTER the base, and their WAL reaches the archive
#    5. Recovery targets are recorded: timestamps, an xid, a named point
#    6. The primary is DESTROYED — recovery starts from the archive alone
#    7-9. Four recoveries, each into a fresh cluster:
#           - to an exact TIMESTAMP
#           - to a TRANSACTION boundary (xid)
#           - to a NAMED restore point
#           - to LATEST (end of WAL)
#   10. Each recovery is verified for what it must CONTAIN and — the part
#       that makes it point-in-time rather than merely a restore — what it
#       must NOT contain.
#
# The assertion that matters: recovering to T must EXCLUDE work committed
# after T. A restore test that only checks rows are present proves the backup
# works, not that the point-in-time does.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

WORKDIR="${PITR_WORKDIR:-/tmp/lacteva-pitr}"
PRIMARY="${WORKDIR}/primary"
ARCHIVE="${WORKDIR}/wal-archive"
BASE="${WORKDIR}/base"
PGPORT_PRIMARY="${PGPORT_PRIMARY:-55432}"
PGPORT_RESTORE="${PGPORT_RESTORE:-55433}"
DB="${PITR_DB:-lacteva_pitr}"

PYTHON="${PYTHON:-services/platform-core/.venv/bin/python}"
[ -x "${PYTHON}" ] || PYTHON="$(command -v python3)"
PYTHON="$(cd "$(dirname "${PYTHON}")" && pwd)/$(basename "${PYTHON}")"

# PostgreSQL binaries come from the pgserver wheel: a real server and a real
# client, no Docker and no root. Same reason verify-postgres.sh uses it — a
# pipeline that cannot run in the environment where the code is written does
# not get run.
BIN="$("${PYTHON}" -c "
import pathlib, pgserver
print(pathlib.Path(pgserver.__file__).parent / 'pginstall' / 'bin')
")"
[ -x "${BIN}/initdb" ] || { echo "PostgreSQL binaries not found at ${BIN}" >&2; exit 2; }
export PATH="${BIN}:${PATH}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mPITR PROOF FAILED: %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }

SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
summary() { printf '%s\n' "$*" >> "${SUMMARY}"; }

cleanup() {
  local status=$?
  for d in "${PRIMARY}" "${WORKDIR}"/restore-*; do
    [ -d "${d}" ] && pg_ctl -D "${d}" -m immediate stop >/dev/null 2>&1 || true
  done
  if [ "${KEEP_CLUSTERS:-0}" = "1" ]; then
    printf '\nKEEP_CLUSTERS=1 — %s left in place.\n' "${WORKDIR}"
  fi
  return "${status}"
}
trap cleanup EXIT

export LACTEVA_ENV=staging
export LACTEVA_EVENT_BUS=memory
export LACTEVA_OUTBOX_MODE=inline
export LACTEVA_CONSUMERS_ENABLED=false
export LACTEVA_RATE_LIMIT_BACKEND=memory
export LACTEVA_MINIO_SECRET_KEY=pitr-proof-not-a-real-secret

# A unix socket needs BOTH the directory and the port: libpq names the socket
# file `.s.PGSQL.<port>`, so a URL carrying only the host silently looks for
# the default 5432 and fails with a bare "No such file or directory".
url() { echo "postgresql+asyncpg://postgres@/${DB}?host=$1&port=${2:-${PGPORT_PRIMARY}}"; }

# =============================================================================
step "1/10  a PostgreSQL configured for continuous archiving"
# =============================================================================
rm -rf "${WORKDIR}"
mkdir -p "${ARCHIVE}" "${PRIMARY}"
initdb -D "${PRIMARY}" -U postgres --auth=trust >/dev/null 2>&1 \
  || fail "initdb failed"

# The three settings PITR actually requires. `wal_level=replica` alone is
# necessary and NOT sufficient — production had exactly that and no archiving,
# which is why the documented 5-minute RPO was fiction.
cat >> "${PRIMARY}/postgresql.conf" <<CONF
port = ${PGPORT_PRIMARY}
unix_socket_directories = '${PRIMARY}'
listen_addresses = ''
wal_level = replica
archive_mode = on
# 'test ! -f' first: the archive is append-only and MUST refuse to overwrite.
# Silently overwriting an archived segment destroys the recovery window
# between the segment it replaced and now.
archive_command = 'test ! -f ${ARCHIVE}/%f && cp %p ${ARCHIVE}/%f'
# Bound the RPO in a quiet period. Without it a low-traffic night can leave
# the last transactions unarchived for hours, because a segment is archived
# when it FILLS, not when it is written.
archive_timeout = 60
max_wal_senders = 4
wal_keep_size = 64MB
CONF

# WO-40: the primary is TUNED, and tuned THE WAY PRODUCTION IS — on the
# command line, not in the data directory's postgresql.conf.
#
# PostgreSQL refuses to replay WAL on an instance whose max_connections (and
# four relatives) are lower than the primary's, and aborts recovery with
# "insufficient parameter settings". This proof ran for months against a
# primary on stock defaults, so its restores — also on stock defaults —
# always matched, and it certified a point-in-time recovery that could not
# actually recover the deployed database, whose max_connections is 200.
#
# The MECHANISM matters as much as the value. Production's compose file runs
# `postgres -c max_connections=200 -c ...`, so those settings live outside
# PGDATA and do NOT travel inside a base backup. Writing them into the
# primary's postgresql.conf here would put them in the backup, the restore
# would inherit them, and the proof would go green while production stayed
# broken — which is precisely how this defect survived. So they go on the
# command line, and the restore has to recover them from the control file.
PRIMARY_TUNING="-c max_connections=200 -c max_worker_processes=12"
PRIMARY_TUNING="${PRIMARY_TUNING} -c max_locks_per_transaction=96"
PRIMARY_TUNING="${PRIMARY_TUNING} -c max_prepared_transactions=4"

pg_ctl -D "${PRIMARY}" -l "${WORKDIR}/primary.log" -o "${PRIMARY_TUNING}" -w -t 60 start >/dev/null \
  || fail "the primary did not start"
psql -h "${PRIMARY}" -p "${PGPORT_PRIMARY}" -U postgres -d postgres -tAc \
  "CREATE DATABASE ${DB}" >/dev/null

ARCHIVING="$(psql -h "${PRIMARY}" -p "${PGPORT_PRIMARY}" -U postgres -d postgres -tAc \
  "SELECT current_setting('archive_mode')")"
[ "${ARCHIVING}" = "on" ] || fail "archive_mode is ${ARCHIVING}, not on"
ok "archive_mode=on, archive_command set, archive_timeout=60s"

# =============================================================================
step "2/10  a realistic dairy, seeded through the platform's own API"
# =============================================================================
(cd services/platform-core \
  && LACTEVA_DATABASE_URL="$(url "${PRIMARY}")" \
     "${PYTHON}" -m alembic upgrade head >/dev/null 2>&1) \
  || fail "migrations did not apply"
(cd services/platform-core \
  && LACTEVA_DATABASE_URL="$(url "${PRIMARY}")" \
     "${PYTHON}" ../../infra/ci/seed_proof_data.py "${WORKDIR}/seed.json" >/dev/null 2>&1) \
  || fail "seeding failed"
"${PYTHON}" -c "
import json
d = json.load(open('${WORKDIR}/seed.json'))
print('    ' + ', '.join(f'{k}={v}' for k, v in d.items() if k != 'organization'))
"
ok "settlement, payment and receipt exist BEFORE the base backup"

# =============================================================================
step "3/10  base backup"
# =============================================================================
pg_basebackup --pgdata="${BASE}" --format=plain --wal-method=stream \
  --checkpoint=fast --progress \
  -h "${PRIMARY}" -p "${PGPORT_PRIMARY}" -U postgres >/dev/null 2>&1 \
  || fail "pg_basebackup failed"
pg_verifybackup "${BASE}" >/dev/null 2>&1 \
  || fail "pg_verifybackup rejected the base backup"
ok "base backup taken and verified against its own manifest"

# =============================================================================
step "4/10  transactions AFTER the base backup, in three labelled batches"
step "5/10  recording recovery targets: timestamps, an xid, a named point"
# =============================================================================
"${PYTHON}" - "${PRIMARY}" "${PGPORT_PRIMARY}" "${DB}" "${WORKDIR}/targets.json" <<'PYEOF'
import asyncio, json, sys
import asyncpg

HOST, PORT, DB, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]


async def main():
    conn = await asyncpg.connect(user="postgres", database=DB, host=HOST, port=PORT)
    # The supplier table is tenant-owned and RLS-protected. A batch write is
    # cross-tenant machinery, so it takes the documented bypass rather than
    # pretending to be a request.
    await conn.execute("SET lacteva.bypass_rls = 'on'")
    tenant = await conn.fetchval("SELECT tenant_id FROM supplier LIMIT 1")
    branch = await conn.fetchval("SELECT branch_id FROM supplier LIMIT 1")

    targets = {}

    async def batch(label, count):
        for i in range(count):
            await conn.execute(
                "INSERT INTO supplier (id, tenant_id, code, status, branch_id,"
                " created_at, updated_at) VALUES"
                " (gen_random_uuid(), $1, $2, 'draft', $3, now(), now())",
                tenant, f"{label}-{i:03d}", branch,
            )

    # --- batch A -----------------------------------------------------------
    await batch("PITRA", 5)
    # A named restore point is the target an operator can actually reason
    # about: "before the migration" beats guessing a timestamp to the second.
    await conn.execute("SELECT pg_create_restore_point('before_batch_b')")
    targets["xid_after_a"] = await conn.fetchval("SELECT txid_current()::text")
    # A timestamp target is compared against COMMIT times. Sleeping a second
    # keeps the boundary unambiguous — two commits inside the same clock tick
    # cannot be separated by a time target, which is a real limitation of
    # recovery_target_time and not a flaw in this test.
    await asyncio.sleep(1.2)
    targets["time_after_a"] = (
        await conn.fetchval("SELECT now()::timestamptz::text")
    )
    await asyncio.sleep(1.2)

    # --- batch B -----------------------------------------------------------
    await batch("PITRB", 7)
    await asyncio.sleep(1.2)
    targets["time_after_b"] = await conn.fetchval("SELECT now()::timestamptz::text")
    await asyncio.sleep(1.2)

    # --- batch C -----------------------------------------------------------
    await batch("PITRC", 3)

    targets["counts"] = {
        "A": await conn.fetchval("SELECT count(*) FROM supplier WHERE code LIKE 'PITRA-%'"),
        "B": await conn.fetchval("SELECT count(*) FROM supplier WHERE code LIKE 'PITRB-%'"),
        "C": await conn.fetchval("SELECT count(*) FROM supplier WHERE code LIKE 'PITRC-%'"),
    }
    targets["settlement_net"] = await conn.fetchval(
        "SELECT net_amount::text FROM settlement LIMIT 1"
    )
    targets["receipt_number"] = await conn.fetchval(
        "SELECT receipt_number FROM receipt LIMIT 1"
    )
    targets["timeline"] = await conn.fetchval(
        "SELECT timeline_id FROM pg_control_checkpoint()"
    )

    # Force every remaining segment into the archive. A segment is archived
    # when it FILLS; without this the last batch would sit in the current
    # segment and be unrecoverable — the archive gap this proof exists to
    # rule out.
    await conn.execute("SELECT pg_switch_wal()")
    await conn.execute("CHECKPOINT")

    json.dump(targets, open(OUT, "w"), indent=2)
    print("    " + json.dumps(targets["counts"]))
    print(f"    named restore point: before_batch_b")
    print(f"    xid after batch A:   {targets['xid_after_a']}")
    print(f"    timeline:            {targets['timeline']}")
    await conn.close()


asyncio.run(main())
PYEOF
[ -s "${WORKDIR}/targets.json" ] || fail "recovery targets were not recorded"
ok "three batches committed; four recovery targets recorded"

# =============================================================================
step "6/10  WAL reached the archive"
# =============================================================================
# Wait for the archiver rather than assuming it kept up. An archive that lags
# is not an archive gap yet — but a proof that reads it too early would
# report one, and a proof that never checks would miss a real gap.
for _ in $(seq 1 60); do
  PENDING="$(psql -h "${PRIMARY}" -p "${PGPORT_PRIMARY}" -U postgres -d "${DB}" -tAc \
    "SELECT count(*) FROM pg_ls_dir('pg_wal/archive_status') AS f WHERE f LIKE '%.ready'")"
  [ "${PENDING}" = "0" ] && break
  sleep 1
done
[ "${PENDING}" = "0" ] || fail "${PENDING} WAL segment(s) never archived — the recovery window has a hole"

FAILED="$(psql -h "${PRIMARY}" -p "${PGPORT_PRIMARY}" -U postgres -d "${DB}" -tAc \
  "SELECT failed_count FROM pg_stat_archiver")"
[ "${FAILED}" = "0" ] || fail "the archiver reported ${FAILED} failures"
SEGMENTS="$(find "${ARCHIVE}" -type f | wc -l)"
[ "${SEGMENTS}" -gt 0 ] || fail "the archive is empty"
ok "${SEGMENTS} segments archived, 0 archiver failures, 0 pending"

# =============================================================================
step "7/10  DESTROYING the primary — recovery now depends on the archive alone"
# =============================================================================
pg_ctl -D "${PRIMARY}" -m immediate stop >/dev/null 2>&1 || true
rm -rf "${PRIMARY}"
[ ! -d "${PRIMARY}" ] || fail "the primary still exists"
ok "primary destroyed; only the base backup and the WAL archive remain"

# =============================================================================
# The recovery driver: restore the base into a fresh directory, recover to a
# target, and report what is present.
# =============================================================================
recover() {
  local label="$1" target_kind="$2" target_value="$3"
  local dir="${WORKDIR}/restore-${label}"

  rm -rf "${dir}"
  cp -a "${BASE}" "${dir}"
  chmod 700 "${dir}"
  rm -f "${dir}/postgresql.auto.conf"

  {
    echo "port = ${PGPORT_RESTORE}"
    echo "unix_socket_directories = '${dir}'"
    echo "listen_addresses = ''"
    # The settings the WAL was WRITTEN with, read from the base backup's own
    # control file — the only honest source, because it describes the cluster
    # the WAL came from rather than whatever a primary is set to today (and by
    # step 7 there is no primary left to ask).
    control="$(pg_controldata "${dir}")"
    for pair in \
      "max_connections:max_connections" \
      "max_worker_processes:max_worker_processes" \
      "max_wal_senders:max_wal_senders" \
      "max_prepared_xacts:max_prepared_transactions" \
      "max_locks_per_xact:max_locks_per_transaction"; do
      label="${pair%%:*}"; guc="${pair##*:}"
      value="$(printf '%s\n' "${control}" | sed -n "s/^${label} setting: *//p" | tr -d '[:space:]')"
      [ -n "${value}" ] && echo "${guc} = ${value}"
    done
    echo "restore_command = 'cp ${ARCHIVE}/%f %p'"
    # A recovered cluster MUST NOT archive into the same archive. Promotion
    # creates a new timeline, and archiving it back would let a later
    # recovery follow the recovered timeline instead of the original —
    # overshooting its target. This is the timeline trap; see PITR.md.
    echo "archive_mode = off"
    # Explicit rather than the 'latest' default, for the same reason.
    echo "recovery_target_timeline = 'current'"
    echo "recovery_target_action = 'promote'"
    case "${target_kind}" in
      time) echo "recovery_target_time = '${target_value}'" ;;
      xid)  echo "recovery_target_xid = '${target_value}'" ;;
      name) echo "recovery_target_name = '${target_value}'" ;;
      latest) : ;;  # no target: replay everything the archive holds
    esac
  } >> "${dir}/postgresql.conf"

  touch "${dir}/recovery.signal"
  pg_ctl -D "${dir}" -l "${WORKDIR}/${label}.log" -w -t 120 start >/dev/null 2>&1 \
    || { tail -20 "${WORKDIR}/${label}.log" >&2; return 1; }

  # Recovery must have FINISHED before anything reads the result.
  #
  # `pg_ctl -w start` returns as soon as the server ACCEPTS CONNECTIONS, and
  # during recovery that happens at "ready to accept read-only connections" —
  # before the recovery target is reached and before promotion. A script that
  # proceeds here gets a read-only database that is still replaying, and
  # whatever it does next either fails confusingly or reads a half-recovered
  # state. `infra/backup/pg-restore-test.sh` had exactly this bug: it ran
  # `alembic upgrade head` immediately after `pg_ctl start`.
  #
  # So poll until promotion completes.
  local in_recovery=t
  for _ in $(seq 1 120); do
    in_recovery="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
      "SELECT pg_is_in_recovery()" 2>/dev/null || echo t)"
    [ "${in_recovery}" = "f" ] && break
    sleep 1
  done
  [ "${in_recovery}" = "f" ] || return 1
  echo "${dir}"
}

# Assert what a recovery CONTAINS and, crucially, what it does NOT.
assert_counts() {
  local dir="$1" label="$2" want_a="$3" want_b="$4" want_c="$5"
  local got_a got_b got_c tl
  got_a="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT count(*) FROM supplier WHERE code LIKE 'PITRA-%'")"
  got_b="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT count(*) FROM supplier WHERE code LIKE 'PITRB-%'")"
  got_c="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT count(*) FROM supplier WHERE code LIKE 'PITRC-%'")"
  tl="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT timeline_id FROM pg_control_checkpoint()")"
  printf '    batches A=%s B=%s C=%s (expected %s/%s/%s), timeline %s\n' \
    "${got_a}" "${got_b}" "${got_c}" "${want_a}" "${want_b}" "${want_c}" "${tl}"
  [ "${got_a}" = "${want_a}" ] && [ "${got_b}" = "${want_b}" ] && [ "${got_c}" = "${want_c}" ] \
    || fail "${label}: recovered to the wrong point — the recovery target was not honoured"
  [ "${tl}" -ge 2 ] || fail "${label}: expected a new timeline after promotion, got ${tl}"
}

# The money must be identical in EVERY recovery: it was committed before the
# base backup, so no recovery target can legitimately change it.
assert_business() {
  local dir="$1" label="$2"
  local net receipt
  net="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT net_amount FROM settlement LIMIT 1")"
  receipt="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT receipt_number FROM receipt LIMIT 1")"
  local want_net want_receipt
  want_net="$("${PYTHON}" -c "import json;print(json.load(open('${WORKDIR}/targets.json'))['settlement_net'])")"
  want_receipt="$("${PYTHON}" -c "import json;print(json.load(open('${WORKDIR}/targets.json'))['receipt_number'])")"
  [ "${net}" = "${want_net}" ] || fail "${label}: settlement is ${net}, expected ${want_net}"
  [ "${receipt}" = "${want_receipt}" ] || fail "${label}: receipt is ${receipt}, expected ${want_receipt}"

  # RLS survives a physical restore or the recovered system leaks tenants.
  local unforced policies
  unforced="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT count(*) FROM pg_class WHERE relrowsecurity AND NOT relforcerowsecurity")"
  policies="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT count(*) FROM pg_policies WHERE schemaname='public'")"
  [ "${unforced}" = "0" ] || fail "${label}: ${unforced} table(s) lost FORCE ROW LEVEL SECURITY"
  [ "${policies}" -gt 30 ] || fail "${label}: only ${policies} policies after recovery"

  # Physical recovery must not have moved the schema.
  local rev
  rev="$(psql -h "${dir}" -p "${PGPORT_RESTORE}" -U postgres -d "${DB}" -tAc \
    "SELECT version_num FROM alembic_version")"
  [ -n "${rev}" ] || fail "${label}: alembic_version is empty"
  printf '    money intact (%s / %s), %s policies, 0 unforced, schema %s\n' \
    "${net}" "${receipt}" "${policies}" "${rev}"
}

stop_restore() { pg_ctl -D "$1" -m fast stop >/dev/null 2>&1 || true; }

TIME_A="$("${PYTHON}" -c "import json;print(json.load(open('${WORKDIR}/targets.json'))['time_after_a'])")"
XID_A="$("${PYTHON}" -c "import json;print(json.load(open('${WORKDIR}/targets.json'))['xid_after_a'])")"

# =============================================================================
step "8/10  recovery to an EXACT TIMESTAMP (${TIME_A})"
# =============================================================================
DIR="$(recover time-a time "${TIME_A}")" || fail "recovery to a timestamp did not complete"
assert_counts "${DIR}" "timestamp" 5 0 0
assert_business "${DIR}" "timestamp"
ok "batches B and C are ABSENT — the target was honoured, not merely restored"
stop_restore "${DIR}"

# =============================================================================
step "9a/10  recovery to a TRANSACTION boundary (xid ${XID_A})"
# =============================================================================
DIR="$(recover xid-a xid "${XID_A}")" || fail "recovery to an xid did not complete"
assert_counts "${DIR}" "xid" 5 0 0
assert_business "${DIR}" "xid"
ok "recovered to a transaction boundary"
stop_restore "${DIR}"

# =============================================================================
step "9b/10  recovery to a NAMED restore point (before_batch_b)"
# =============================================================================
DIR="$(recover name-a name "before_batch_b")" || fail "recovery to a named point did not complete"
assert_counts "${DIR}" "named" 5 0 0
assert_business "${DIR}" "named"
ok "recovered to an operator-meaningful name, not a guessed timestamp"
stop_restore "${DIR}"

# =============================================================================
step "9c/10  recovery to LATEST (end of the archive)"
# =============================================================================
DIR="$(recover latest latest "")" || fail "recovery to latest did not complete"
assert_counts "${DIR}" "latest" 5 7 3
assert_business "${DIR}" "latest"
ok "every committed transaction recovered — nothing lost to the archive"

# =============================================================================
step "10/10  the recovered platform passes its own business rules"
# =============================================================================
(cd services/platform-core \
  && LACTEVA_DATABASE_URL="$(url "${DIR}" "${PGPORT_RESTORE}")" \
     "${PYTHON}" -m platform_core.core.backup.cli integrity --deep > "${WORKDIR}/integrity.json" 2>/dev/null) \
  || fail "the recovered database violates the platform's own business rules"
"${PYTHON}" - "${WORKDIR}/integrity.json" <<'PYEOF'
import json, sys
lines = open(sys.argv[1]).read().splitlines()
start = max(i for i, line in enumerate(lines) if line == "{")
report = json.loads("\n".join(lines[start:]))
checks = report.get("integrity", {}).get("checks") or report.get("checks") or []
failed = [c["name"] for c in checks if not c.get("passed", True)]
assert not failed, f"integrity checks failed: {failed}"
print(f"    {len(checks)} business integrity checks passed on the recovered data")
PYEOF
stop_restore "${DIR}"

# =============================================================================
summary "## Point-in-Time Recovery — proven"
summary ""
summary "| Recovery target | Result |"
summary "| --- | --- |"
summary "| Exact timestamp | batch A only — later work correctly excluded |"
summary "| Transaction boundary (xid) | batch A only |"
summary "| Named restore point | batch A only |"
summary "| Latest | all three batches, nothing lost |"
summary ""
summary "Money, receipts, RLS policies and schema revision identical in every recovery."

cat <<'BANNER'

╭──────────────────────────────────────────────────────────────╮
│  POINT-IN-TIME RECOVERY PROVEN                               │
│                                                              │
│  continuous WAL archiving ..... proven                       │
│  base backup + verify ......... proven                       │
│  primary destroyed ............ recovery from archive alone   │
│  recovery to a timestamp ...... proven                       │
│  recovery to a transaction .... proven                       │
│  recovery to a named point .... proven                       │
│  recovery to latest ........... proven                       │
│  work after the target ........ correctly EXCLUDED           │
│  money / receipts / RLS ....... intact in every recovery     │
╰──────────────────────────────────────────────────────────────╯
BANNER
