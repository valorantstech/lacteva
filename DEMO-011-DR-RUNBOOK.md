---
id: DEMO-011-DR-RUNBOOK
title: Disaster Recovery Runbook
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-13
last-updated: 2026-08-13
related: [DEMO-011-FINAL, BACKUP, RESTORE, PITR, RUNBOOK-BACKUP]
baseline: ARCH-BASELINE-V1
---

# Disaster Recovery Runbook

For the person who has to fix it, at the hour it breaks. Commands are literal
and can be pasted. Everything here has been executed on the deployment, not
reasoned about.

**Read §11 first if you are in a hurry.** It is the list of things that turn a
recoverable incident into an unrecoverable one.

---

## 1. Where backups are

Three copies, on two devices and in two regions.

| What | Where | Device | Holds |
| --- | --- | --- | --- |
| Logical backups | `/var/lib/lacteva/backup/logical/<UTC stamp>/` | `/dev/nvme1n1` (49 GB, mounted at `/var/lib/lacteva`) | Every table, type-tagged JSONL, per-table checksums. ~17 MB each |
| Physical base backups | `/var/lib/lacteva/backup/base/<UTC stamp>/` | same | `pg_basebackup`, plain format, `pg_verifybackup`-checked. ~950 MB each |
| WAL archive | `/var/lib/lacteva/wal-archive/` | same | 16 MB segments; with a base backup this gives point-in-time recovery |
| Off-site | `s3://lacteva-offsite-backups-590182060076` (`ap-southeast-1`) | S3 | The logical backup, tar + manifest, checksum verified on upload |

**The database is on a different device** — `/dev/nvme0n1p1`, the root disk.
That separation is the point: losing the database's disk does not lose the
backups. Inside the API container the same directory is `/backup`.

The quarantine directory `/var/lib/lacteva/backup/quarantine/` holds artefacts
withdrawn from service (currently one truncated WAL segment). Nothing there is
a recovery point.

---

## 2. Schedule

| Unit | When (UTC) | What it does |
| --- | --- | --- |
| `lacteva-backup-nightly.timer` | daily 02:15 | Logical backup → verify → replicate off-site → prune |
| `lacteva-backup-weekly.timer` | Sunday 03:30 | `pg_basebackup` → `pg_verifybackup` → prune bases → prune WAL |
| `lacteva-backup-verify.timer` | Saturday 05:00 | Restore drill into a throwaway server (§6) |
| `lacteva-backup-watchdog.timer` | 06:40, 14:40, 22:40 | Is there a current, verified recovery point? |
| `lacteva-disk-guard.timer` | every 6h | Reclaims disk; reports the backup volume |

All are `Persistent=true`, so a host that was off when one was due runs it on
return.

```bash
systemctl list-timers 'lacteva-*'      # what is scheduled
```

---

## 3. Retention

| Artefact | Kept | Enforced by |
| --- | --- | --- |
| Logical backups | 30 days | `run-logical-backup.sh`, after a successful verified backup |
| Off-site copies | 30 | `backup.cli offsite-prune`, never below 1, never the newest |
| Base backups | 35 days | `pg-backup.sh` |
| WAL segments | Whatever the **oldest retained base backup** still needs | `pg_archivecleanup`, against the `.backup` label — never against a date |

Pruning always happens **after** a successful backup, never before. The worst
case is too many copies.

WAL is not pruned by age. A base backup without the WAL that follows it is a
snapshot, not point-in-time recovery, so the archive is cut to the oldest base
backup still on disk and no further.

---

## 4. Finding the newest valid backup

```bash
# The platform's own answer, including whether it VERIFIED
cd /opt/lacteva/current
sudo docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production \
  exec -T api python -m platform_core.core.backup.cli status

# The watchdog's answer, written three times a day
cat /var/log/lacteva/backup-status

# The files themselves, newest first BY TIME (names sort wrongly — see below)
sudo ls -1t /var/lib/lacteva/backup/logical | head -5
sudo ls -1t /var/lib/lacteva/backup/base | head -3
```

**Do not sort backup names alphabetically.** `predeploy-20260812T220548Z`
sorts after `20260813T121038Z` because `p` > `2`. Two naming schemes share
that directory: scheduled backups are bare timestamps, `deploy.sh` writes
`predeploy-<stamp>` before every upgrade. Sort by modification time.

Re-verify a specific backup without restoring it:

```bash
sudo docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production \
  exec -T api python -m platform_core.core.backup.cli verify /backup/logical/<stamp>
```

Off-site copies:

```bash
sudo docker compose ... exec -T api python -m platform_core.core.backup.cli offsite-list
sudo docker compose ... exec -T api python -m platform_core.core.backup.cli offsite-fetch <backup-id> /backup/logical/<stamp>
```

---

## 5. Restoring

### 5.1 Decide which kind

| Situation | Use |
| --- | --- |
| Data is wrong, database is healthy | **Logical restore** (§5.2) — the data, not the machine |
| Database will not start; disk intact | **Physical restore** (§5.3) |
| You need a specific moment ("just before 14:32") | **Point-in-time recovery** (§5.4) |
| The instance is gone | **Rebuild** (§9), then §5.2 or §5.3 |

### 5.2 Logical restore

**This overwrites the database it is pointed at.** Check
`LACTEVA_DATABASE_URL` twice.

```bash
cd /opt/lacteva/current
C="sudo docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production"

$C stop api                                     # stop writers first
$C exec -T api python -m platform_core.core.backup.cli backup /backup/logical/pre-restore-$(date -u +%Y%m%dT%H%M%SZ)
$C run --rm --no-deps -T api alembic upgrade head
$C run --rm --no-deps -T api python -m platform_core.core.backup.cli restore /backup/logical/<stamp>
$C run --rm --no-deps -T api python -m platform_core.core.backup.cli integrity --deep
$C up -d api
```

Take a backup **before** restoring, even in an emergency. It costs seconds and
it is the only way back if the backup you chose turns out to be the wrong one.

### 5.3 Physical restore

```bash
cd /opt/lacteva/current
C="sudo docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production"

$C stop api portal nginx
$C stop postgres
sudo mv /var/lib/docker/volumes/lacteva-production_pgdata/_data \
        /var/lib/docker/volumes/lacteva-production_pgdata/_data.before-restore
sudo mkdir -p /var/lib/docker/volumes/lacteva-production_pgdata/_data
sudo cp -a /var/lib/lacteva/backup/base/<stamp>/. \
           /var/lib/docker/volumes/lacteva-production_pgdata/_data/
sudo chown -R 999:999 /var/lib/docker/volumes/lacteva-production_pgdata/_data
$C up -d postgres && sleep 20
$C exec -T postgres pg_isready -U lacteva
$C up -d
```

`mv` the old data directory; do not delete it. It is your second chance.

### 5.4 Point-in-time recovery

`infra/backup/pg-restore-test.sh` performs this into a throwaway instance and
is the rehearsal. For a real recovery, restore the base backup as in §5.3,
then before starting PostgreSQL:

```bash
sudo tee /var/lib/docker/volumes/lacteva-production_pgdata/_data/recovery.signal >/dev/null </dev/null
sudo tee -a /var/lib/docker/volumes/lacteva-production_pgdata/_data/postgresql.auto.conf >/dev/null <<'CONF'
restore_command = 'cp /wal-archive/%f %p'
recovery_target_time = '2026-08-13 14:32:00+00'
recovery_target_action = 'promote'
CONF
```

Then start PostgreSQL and watch the log until it reports consistent recovery.

---

## 6. Verifying a restore

The drill does all of this and is the thing to run:

```bash
sudo systemctl start lacteva-backup-verify.service
sudo tail -60 /var/log/lacteva/backup-verify.log
```

It restores the newest backup into a **separate throwaway PostgreSQL server**,
applies migrations, runs `integrity --deep` (which rebuilds every projection
from the restored event log), then compares against production **per table**
and **by money**, and removes the drill server and its data on every exit path.

After a real restore, the equivalent by hand:

```bash
$C run --rm --no-deps -T api python -m platform_core.core.backup.cli integrity --deep
curl -s https://dev.phoenixsoft.in/health/ready | python3 -m json.tool
```

Then check the business: sign in, open the dashboard, confirm the receivable
and a known customer's balance.

---

## 7. Services: what to stop, and in what order

**Stop** (writers first, so nothing is mid-transaction):

```
api → portal → nginx → postgres
```

**Start** (dependencies first; compose enforces this by health check):

```
postgres → redis → rabbitmq → api → portal → nginx
```

```bash
sudo systemctl stop lacteva.service     # graceful, honours stop_grace_period
sudo systemctl start lacteva.service
```

`lacteva.service` is `Type=oneshot` with `RemainAfterExit`: systemd starts and
stops the stack, Docker supervises the containers. Do not try to make systemd
supervise containers as well.

---

## 8. Recovering the application containers

The images are in ECR and the release directories are on disk.

```bash
# What is running, and what it should be
grep '^LACTEVA_IMAGE_TAG=' /etc/lacteva/.env.production
sudo ls -1t /opt/lacteva/releases | head -5

# Redeploy a known-good tag (pull → backup → migrate → verify → smoke test)
sudo /opt/lacteva/current/infra/deploy/deploy.sh <tag>

# Or go back one release
sudo /opt/lacteva/current/infra/deploy/deploy.sh --rollback
```

The host pulls from ECR using the instance role via
`docker-credential-ecr-login`; there is no stored token to expire.

---

## 9. If the database host is gone

1. **Launch** a replacement EC2 from the same AMI family, `c7i-flex.large`,
   in `ap-south-1`. Attach a data volume at `/var/lib/lacteva`.
2. **Reattach the Elastic IP** `15.252.65.201`, so DNS and TLS need no change.
3. **Install** Docker and the units:
   ```bash
   sudo install -d -o 999 -g 999 -m 0700 \
     /var/lib/lacteva/backup/logical /var/lib/lacteva/backup/base /var/lib/lacteva/wal-archive
   sudo install -m 0644 /opt/lacteva/current/infra/systemd/lacteva*.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now lacteva.service
   ```
4. **Restore the secret** `/etc/lacteva/.env.production` (root, 0600). Without
   it nothing starts. It is not in git, by design.
5. **Fetch a backup from S3** — the only copy that survives the instance:
   ```bash
   $C exec -T api python -m platform_core.core.backup.cli offsite-list
   $C exec -T api python -m platform_core.core.backup.cli offsite-fetch <id> /backup/logical/recovered
   ```
6. **Restore** per §5.2 and **verify** per §6.

**If both the instance and its volumes are lost, the off-site logical backup
is the only recovery point** — so recovery is to the last nightly, and the WAL
archive is gone with the machine. That is the honest limit of a single-host
deployment; see DEMO-011-FINAL.md §Known limitations.

---

## 10. How long it takes

Measured on this deployment, 28,241 rows / 17 MB logical / 950 MB base.

| Step | Time |
| --- | --- |
| Logical backup + verify + off-site | ~5 s |
| Physical base backup + verify | ~25 s |
| Full restore drill (start server, migrate, restore, deep integrity, compare) | ~60 s |
| Logical restore into the live database | ~10 s + migrations |
| Redeploy the application | ~90 s |
| Rebuild the host from nothing (§9) | 30–60 min, mostly launching and installing |

**RPO** — 24 h from the nightly logical backup; a few minutes if the WAL
archive survives (`archive_timeout=60`). **RTO** — minutes for data, under an
hour for a full host rebuild.

---

## 11. Never do these

1. **Never restore over production to "check the backup".** Use
   `lacteva-backup-verify.service`, which restores into a separate throwaway
   server and cannot reach the live database.
2. **Never delete a recovery point to free space.** Retention is in the
   scripts and knows which copies are still needed. Deleting a WAL segment by
   hand can silently make a base backup unrestorable.
3. **Never `rm -rf` the old data directory during a restore.** `mv` it. It is
   your second chance.
4. **Never skip the pre-restore backup**, however urgent it feels.
5. **Never overwrite an archived WAL segment.** `archive-wal.sh` refuses a
   same-name-different-content collision on purpose. If it refuses, look —
   do not force it.
6. **Never prune before a backup has succeeded and verified.**
7. **Never trust a green dashboard as evidence of a backup.** The platform
   reported `healthy: verified backup 12.8 hours old` while having no backup
   schedule at all — the file it saw was taken incidentally by a deployment.
   Check `systemctl list-timers` and `/var/log/lacteva/backup-status`.
8. **Never leave a restored copy of production data on the machine.** The
   drill removes its server and volume on every exit path, including failure.
9. **Never put backups on the database's device.** They are on
   `/var/lib/lacteva` for that reason.

---

## 12. Ten-second health check

```bash
cat /var/log/lacteva/backup-status          # protected=yes
ls /var/log/lacteva/BACKUP-FAILED           # should NOT exist
systemctl list-timers 'lacteva-*'           # four backup timers scheduled
```

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-13 | Written for DEMO-011, after making every mechanism in it actually run. |
