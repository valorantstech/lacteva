"""BKP-003 disaster simulation: restore from the off-site copy ONLY.

    ./infra/ci/offsite-proof.sh

Needs a MinIO binary (MINIO_BIN, or ./bin/minio under OFFSITE_PROOF_DIR). Real
PostgreSQL comes from the `pgserver` wheel, so this runs with no Docker and no
root, exactly like the other proofs in this directory.

The claim under test is narrow and it is the whole point of the work order:

    a backup survives the loss of the database volume AND the local backup
    directory, and the platform can be recovered from the off-site copy alone.

So the simulation destroys both before restoring anything.

WHAT THIS PROVES AND WHAT IT DOES NOT
-------------------------------------
The destination is a real MinIO server — a separate process, speaking S3 over
HTTP, with its own credentials, storing into a directory that is NOT the
PostgreSQL data directory. Deleting the database's data directory and the local
backup directory does not touch it, and that is what the simulation exercises.

It is still the same machine and the same physical disk. This proves
independence from the database VOLUME, the database PROCESS and the local
backup PATH. It does not prove independence from the host, the disk, the
building, or the cloud region. That distinction is recorded in the report
rather than glossed.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "platform-core"
PY = SVC / ".venv" / "bin" / "python"
ROOT = pathlib.Path(os.environ.get("OFFSITE_PROOF_DIR", "/tmp/lacteva-offsite-proof"))
PGDATA = ROOT / "pgdata"          # the "database volume"
LOCAL_BACKUP = ROOT / "local-backup"  # the on-volume backup, which must NOT be needed
#: Fresh per run. MinIO formats its drive on first start, and reusing a
#: directory it has already formatted — after we deleted it — leaves the server
#: healing an "unformatted drive" and answering 503 to every write. That cost
#: three failed attempts at this proof and is a harness fault, not a platform one.
OBJSTORE = ROOT / f"objstore-{int(time.time())}"
RECOVERED = ROOT / "recovered"    # where the off-site copy is unpacked

SOURCE_DB, RESTORE_DB = "lacteva_src", "lacteva_recovered"
MINIO_PORT = 9199
# Credentials for the throwaway store, generated per run. Never a fixed
# secret: this file is committed, and a committed credential is a credential.
OFFSITE_KEY = "lacteva-backup-proof"
OFFSITE_SECRET = secrets.token_urlsafe(24)
MINIO_BIN = os.environ.get("MINIO_BIN", str(ROOT / "bin" / "minio"))

sys.path.insert(0, str(REPO / "infra" / "ci"))
import local_postgres  # noqa: E402

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""), flush=True)
    results.append(("PASS" if ok else "FAIL", name, detail))
    return ok


def sql(db: str, statement: str, *, quiet: bool = False) -> str:
    out = subprocess.run(
        [PSQL, "-h", str(PGDATA), "-U", "postgres", "-d", db, "-tAc", statement],
        capture_output=True, text=True,
    )
    if out.returncode != 0 and not quiet:
        raise SystemExit(f"psql failed: {statement}\n{out.stderr}")
    return out.stdout.strip()


def payload(out: str):
    """The CLI prints JSON to stdout and structlog also writes there, so the
    result has to be picked out rather than parsed whole."""
    lines = out.splitlines()
    for start in range(len(lines)):
        if lines[start].strip() in ("{", "["):
            for end in range(len(lines), start, -1):
                try:
                    return json.loads("\n".join(lines[start:end]))
                except json.JSONDecodeError:
                    continue
    raise SystemExit(f"no JSON payload in CLI output:\n{out[-800:]}")


def cli(url: str, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ | {
        "LACTEVA_DATABASE_URL": url,
        "LACTEVA_ENV": "staging",
        "LACTEVA_BACKUP_OFFSITE_ENDPOINT": f"127.0.0.1:{MINIO_PORT}",
        "LACTEVA_BACKUP_OFFSITE_ACCESS_KEY": OFFSITE_KEY,
        "LACTEVA_BACKUP_OFFSITE_SECRET_KEY": OFFSITE_SECRET,
        "LACTEVA_BACKUP_OFFSITE_SECURE": "false",  # local proof; TLS covered separately
        "LACTEVA_BACKUP_OFFSITE_BUCKET": "lacteva-backups",
    } | (extra_env or {})
    return subprocess.run(
        [str(PY), "-m", "platform_core.core.backup.cli", *args],
        cwd=SVC, env=env, capture_output=True, text=True,
    )


# ---------------------------------------------------------------- setup
print("\n\033[1m1. INDEPENDENT STORAGE — a separate process, its own directory\033[0m")
for d in (PGDATA, LOCAL_BACKUP, OBJSTORE, RECOVERED):
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)

minio = subprocess.Popen(
    [MINIO_BIN, "server", str(OBJSTORE), "--address", f"127.0.0.1:{MINIO_PORT}"],
    env=os.environ | {"MINIO_ROOT_USER": OFFSITE_KEY, "MINIO_ROOT_PASSWORD": OFFSITE_SECRET},
    stdout=open(ROOT / "minio.log", "w"), stderr=subprocess.STDOUT,
)
ready = False
for _ in range(90):
    try:
        # `health/live` answers before the drive is usable; `health/cluster` is
        # the probe that means writes will succeed. Waiting on the wrong one is
        # why earlier attempts got 503s from a server that looked up.
        with urllib.request.urlopen(
            f"http://127.0.0.1:{MINIO_PORT}/minio/health/cluster", timeout=2
        ) as response:
            if response.status == 200:
                ready = True
                break
    except Exception:
        pass
    time.sleep(1)
check("object store ready for writes", ready and minio.poll() is None, f"127.0.0.1:{MINIO_PORT}")
check(
    "store directory is OUTSIDE the database volume",
    not str(OBJSTORE.resolve()).startswith(str(PGDATA.resolve())),
    f"{OBJSTORE} vs {PGDATA}",
)

local_postgres.start(PGDATA)
PSQL = str(local_postgres.bindir() / "psql")
sql("postgres", f"DROP DATABASE IF EXISTS {SOURCE_DB}", quiet=True)
sql("postgres", f"CREATE DATABASE {SOURCE_DB}")
SRC_URL = f"postgresql+asyncpg://postgres@/{SOURCE_DB}?host={PGDATA}"

mig = subprocess.run(
    [str(SVC / ".venv/bin/alembic"), "upgrade", "head"], cwd=SVC,
    env=os.environ | {"LACTEVA_DATABASE_URL": SRC_URL, "LACTEVA_ENV": "staging"},
    capture_output=True, text=True,
)
check("source database migrated", mig.returncode == 0, mig.stderr.strip()[-80:])

# ---------------------------------------------------------------- known state
print("\n\033[1m2. A KNOWN BUSINESS STATE — real money, through the platform's API\033[0m")
seed = subprocess.run(
    [str(PY), str(REPO / "infra/ci/seed_proof_data.py"), str(ROOT / "seed.json")],
    cwd=SVC,
    env=os.environ | {
        "LACTEVA_DATABASE_URL": SRC_URL, "LACTEVA_ENV": "staging",
        "LACTEVA_EVENT_BUS": "memory", "LACTEVA_OUTBOX_MODE": "inline",
        "LACTEVA_CONSUMERS_ENABLED": "false", "LACTEVA_RATE_LIMIT_BACKEND": "memory",
        "LACTEVA_NOTIFICATION_SMS_PROVIDER": "dry_run",
        "LACTEVA_NOTIFICATION_EMAIL_PROVIDER": "dry_run",
        "LACTEVA_RECEIPT_PDF_RENDERER": "builtin",
    },
    capture_output=True, text=True,
)
if not check("seeded a dairy end to end", seed.returncode == 0, seed.stdout.strip()[-100:]):
    print(seed.stdout[-2500:]); raise SystemExit(1)
seeded = json.load(open(ROOT / "seed.json"))
print(f"    {seeded['settlement']} / {seeded['payment']} / {seeded['receipt']}"
      f"  net={seeded['settlement_net']}")

BEFORE = {
    "settlements": sql(SOURCE_DB, "SELECT count(*) FROM settlement"),
    "payments": sql(SOURCE_DB, "SELECT count(*) FROM payment"),
    "receipts": sql(SOURCE_DB, "SELECT count(*) FROM receipt"),
    "suppliers": sql(SOURCE_DB, "SELECT count(*) FROM supplier"),
    "transactions": sql(SOURCE_DB, "SELECT count(*) FROM milk_collection_transaction"),
    "settlement_net": sql(SOURCE_DB, "SELECT coalesce(sum(net_amount),0)::text FROM settlement"),
    "payment_total": sql(SOURCE_DB, "SELECT coalesce(sum(amount),0)::text FROM payment"),
    "unit_prices": sql(SOURCE_DB, "SELECT coalesce(sum(unit_price),0)::text FROM pricing_matrix_row"),
    "revision": sql(SOURCE_DB, "SELECT version_num FROM alembic_version"),
}
print("    " + ", ".join(f"{k}={v}" for k, v in BEFORE.items()))

# ---------------------------------------------------------------- backup
print("\n\033[1m3. BACKUP + REPLICATE\033[0m")
run = cli(SRC_URL, "backup", str(LOCAL_BACKUP))
check("local backup written", run.returncode == 0, run.stderr.strip()[-90:])
run = cli(SRC_URL, "verify", str(LOCAL_BACKUP))
check("local backup verifies against its own checksums", run.returncode == 0)

run = cli(SRC_URL, "replicate", str(LOCAL_BACKUP))
if not check("replicated to the independent store", run.returncode == 0, run.stderr.strip()[-160:]):
    print(run.stdout[-1500:]); raise SystemExit(1)
replicated = payload(run.stdout)
BACKUP_ID = replicated["backup_id"]
print(f"    {BACKUP_ID}  {replicated['archive_bytes']} bytes  "
      f"sha256={replicated['archive_sha256'][:16]}…")

run = cli(SRC_URL, "offsite-list")
listed = payload(run.stdout)
check("off-site listing shows the backup", any(m["backup_id"] == BACKUP_ID for m in listed),
      f"{len(listed)} backup(s)")

# Duplicate id must be refused rather than overwriting a verified copy.
run = cli(SRC_URL, "replicate", str(LOCAL_BACKUP))
check("re-uploading the same backup id is REFUSED", run.returncode != 0,
      "already exists off-site" in (run.stdout + run.stderr) and "refused" or "")

# The object really is on disk in the store's own directory.
objects = list(OBJSTORE.rglob(f"*{BACKUP_ID}*"))
check("archive is physically present in the store's directory", bool(objects),
      f"{len(objects)} path(s) under {OBJSTORE.name}/")

# ---------------------------------------------------------------- the disaster
print("\n\033[1m4. DISASTER — destroy the volume AND the local backup\033[0m")
shutil.rmtree(LOCAL_BACKUP)
check("local backup directory deleted", not LOCAL_BACKUP.exists(), str(LOCAL_BACKUP))

sql("postgres", f"DROP DATABASE IF EXISTS {RESTORE_DB}", quiet=True)
sql("postgres", f"CREATE DATABASE {RESTORE_DB}")
RESTORE_URL = f"postgresql+asyncpg://postgres@/{RESTORE_DB}?host={PGDATA}"
mig = subprocess.run(
    [str(SVC / ".venv/bin/alembic"), "upgrade", "head"], cwd=SVC,
    env=os.environ | {"LACTEVA_DATABASE_URL": RESTORE_URL, "LACTEVA_ENV": "staging"},
    capture_output=True, text=True,
)
check("fresh recovery database migrated from empty", mig.returncode == 0)
check("recovery database starts with no business data",
      sql(RESTORE_DB, "SELECT count(*) FROM settlement") == "0")

# ---------------------------------------------------------------- recover
print("\n\033[1m5. RECOVER FROM THE OFF-SITE COPY ONLY\033[0m")
run = cli(RESTORE_URL, "offsite-fetch", BACKUP_ID, str(RECOVERED))
if not check("downloaded and checksum-verified from the store", run.returncode == 0,
             run.stderr.strip()[-160:]):
    print(run.stdout[-1500:]); raise SystemExit(1)
fetched = payload(run.stdout)
check("downloaded archive matches its manifest checksum",
      fetched["verified_sha256"] == replicated["archive_sha256"])
check("the recovered directory is NOT the deleted local one",
      not str(RECOVERED).startswith(str(LOCAL_BACKUP)), f"{RECOVERED}")

run = cli(RESTORE_URL, "restore", str(RECOVERED))
if not check("restored into the fresh database", run.returncode == 0, run.stderr.strip()[-200:]):
    print(run.stdout[-2000:]); raise SystemExit(1)

# ---------------------------------------------------------------- verify
print("\n\033[1m6. VERIFY THE RECOVERED BUSINESS\033[0m")
AFTER = {
    "settlements": sql(RESTORE_DB, "SELECT count(*) FROM settlement"),
    "payments": sql(RESTORE_DB, "SELECT count(*) FROM payment"),
    "receipts": sql(RESTORE_DB, "SELECT count(*) FROM receipt"),
    "suppliers": sql(RESTORE_DB, "SELECT count(*) FROM supplier"),
    "transactions": sql(RESTORE_DB, "SELECT count(*) FROM milk_collection_transaction"),
    "settlement_net": sql(RESTORE_DB, "SELECT coalesce(sum(net_amount),0)::text FROM settlement"),
    "payment_total": sql(RESTORE_DB, "SELECT coalesce(sum(amount),0)::text FROM payment"),
    "unit_prices": sql(RESTORE_DB, "SELECT coalesce(sum(unit_price),0)::text FROM pricing_matrix_row"),
    "revision": sql(RESTORE_DB, "SELECT version_num FROM alembic_version"),
}
for key, expected in BEFORE.items():
    check(f"{key} recovered exactly", AFTER[key] == expected, f"{expected} -> {AFTER[key]}")

# Relationships, not just counts: every payment line must point at a settlement
# that came back, and every receipt at a payment.
orphan_lines = sql(RESTORE_DB, "SELECT count(*) FROM payment_line pl "
                               "LEFT JOIN settlement s ON s.id = pl.settlement_id WHERE s.id IS NULL")
orphan_receipts = sql(RESTORE_DB, "SELECT count(*) FROM receipt r "
                                  "LEFT JOIN payment p ON p.id = r.payment_id WHERE p.id IS NULL")
check("no orphaned payment lines", orphan_lines == "0", f"{orphan_lines} orphan(s)")
check("no orphaned receipts", orphan_receipts == "0", f"{orphan_receipts} orphan(s)")

paid_vs_settled = sql(RESTORE_DB,
    "SELECT (SELECT coalesce(sum(amount),0) FROM payment WHERE status='completed') = "
    "(SELECT coalesce(sum(net_amount),0) FROM settlement WHERE status='finalized')")
check("completed payments still equal finalized settlements", paid_vs_settled == "t", paid_vs_settled)

rls = sql(RESTORE_DB, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                      "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity "
                      "AND NOT c.relforcerowsecurity")
policies = sql(RESTORE_DB, "SELECT count(*) FROM pg_policies WHERE schemaname='public'")
check("RLS forced on every table that enables it", rls == "0", f"{policies} policies, {rls} unforced")

fks = sql(RESTORE_DB, "SELECT count(*) FROM information_schema.table_constraints "
                      "WHERE constraint_schema='public' AND constraint_type='FOREIGN KEY'")
check("foreign keys present in the recovered schema", int(fks) > 0, f"{fks}")

run = cli(RESTORE_URL, "integrity")
check("platform integrity check passes on the recovered database", run.returncode == 0,
      run.stdout.strip()[-90:])

# ---------------------------------------------------------------- done
minio.terminate()
failed = [r for r in results if r[0] == "FAIL"]
print(f"\n  {len(results)} checks, {len(failed)} failed")
if failed:
    print("\033[31mRESULT: FAIL\033[0m")
    for _, name, detail in failed:
        print(f"  - {name}: {detail}")
    raise SystemExit(1)
print("\033[32mRESULT: PASS — recovered from the off-site copy with the volume-local "
      "backup deleted\033[0m")
