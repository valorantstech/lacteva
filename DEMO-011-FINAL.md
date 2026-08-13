---
id: DEMO-011-FINAL
title: DEMO-011 — Backup, Disaster Recovery & Data Safety
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-13
last-updated: 2026-08-13
related: [DEMO-011-DR-RUNBOOK, DEMO-010-FINAL, BACKUP, RESTORE, PITR]
baseline: ARCH-BASELINE-V1
---

# DEMO-011 — Backup, Disaster Recovery & Data Safety

This platform had a backup engine that checksums and self-verifies, a restore
verifier, a physical backup script, point-in-time recovery machinery, three
systemd timers, a health probe that goes red at 26 hours, and documentation
describing all of it.

**None of it ran.**

Not one of the three backup units was installed. The `lacteva.service` they
all declare a dependency on did not exist either. Every backup on the machine
had been taken incidentally by `deploy.sh` before an upgrade, and the
platform's own health probe reported

> `"healthy": true, "detail": "verified backup 12.8 hours old"`

because somebody had happened to deploy the previous evening.

DEMO-011 is almost entirely the work of making written guarantees execute, and
of finding out — by running them — that several of them could never have
worked at all.

**No application deployment was required.** The one application change is an
alert rule; the rest is infrastructure. **AWS cost impact: none.**

---

## 1. What was actually true before

Verified rather than assumed, as §1 required.

| Claim in the repository | Reality on the machine |
| --- | --- |
| Nightly logical backup at 02:15 | Unit not installed. Never ran. |
| Weekly physical backup on Sundays | Unit not installed. Also **could never have run** (§3) |
| Weekly restore verification | Unit not installed. Never ran. |
| `lacteva.service` starts the stack on boot | **Did not exist.** The stack survives reboot only because Docker's `restart: unless-stopped` brings containers back |
| Backups are off the database's storage | Both were Docker named volumes on the **same block device** as `pgdata` |
| WAL archive is on separate storage from `pgdata` | Same device. The compose comment saying otherwise was aspirational |
| WAL archiving gives a ~5 minute RPO | **Archiving had been dead for 18 hours** (§2) |
| Off-site replication to S3 | Configured, and had run **once**, on 2026-08-09: two objects, 80 KB |
| A 49 GB data volume is mounted at `/var/lib/lacteva` | True, and **empty at 1%** — see below |

The empty data volume has a specific cause worth recording. Provisioning ran
`mkdir -p /var/lib/lacteva/{postgres,redis,prometheus,loki,grafana}` under a
shell without brace expansion, creating **one directory named
`{postgres,redis,prometheus,loki,grafana}`**. A second, `{logical,base,wal}`,
sat inside `backup/`. Everything therefore went to Docker's default location
on the root disk, which is why that disk reached 100% twice during DEMO-009
while a purpose-provisioned 47 GB sat unused.

---

## 2. The most serious finding: WAL archiving was dead

`archive_command` was PostgreSQL's own documented example:

```
test ! -f /wal-archive/%f && cp %p /wal-archive/%f
```

`cp` is not atomic. A copy interrupted at **2026-08-12T17:41Z** left 3,342,336
bytes of a 16,777,216-byte segment at the destination. `test ! -f` then saw a
file, returned non-zero, and PostgreSQL retried **the same segment every
second for the next eighteen hours**.

Consequences, none of which produced an alert:

- **No WAL was archived at all** in that window, so point-in-time recovery had
  a silent hole across it.
- **58 segments, 945 MB**, accumulated in `pg_wal` — on the database's own
  disk — and were still climbing.
- PostgreSQL logs a warning and keeps serving. The container stayed *healthy*.

This is very likely the mechanism behind DEMO-009's two disk-full events.

**The fix is `infra/backup/archive-wal.sh`**, and it addresses the class:

| Rule | Why |
| --- | --- |
| Write to a temp file, then `rename` | Atomic within a filesystem. The destination never exists in a partial state; an interruption leaves an inert temp file |
| A byte-identical file already present is **success** | PostgreSQL legitimately re-archives after a crash. Failing that would wedge it for exactly the original reason |
| Same name, **different** content is a hard failure | Timelines have diverged or the archive is corrupt. Silently overwriting destroys a recovery point |
| `fsync` before the rename | A rename that survives a crash while its data does not is an archive full of promises |

All four are demonstrated, not asserted:

```
1. fresh archive:              OK
2. same bytes again:           OK (idempotent)
3. DIFFERENT bytes, same name: REFUSED (exit 1) - correct
4. the archived copy is still the original: YES
5. no temp files left behind:  clean
```

The truncated segment was **quarantined, not deleted**
(`backup/quarantine/…C4.truncated-20260812T1741Z`). PostgreSQL re-archived the
good copy from `pg_wal`; the archive drained from 58 queued to zero.

---

## 3. The physical backup could never have worked

Three independent defects, none observed because the unit had never executed.

1. **It ran on the host and could not reach the database.** It failed on line
   one with `PGHOST: set PGHOST`, and would have failed on the next line
   anyway: the database port is deliberately not published. A base backup
   taken from the host could never have connected to anything.
   `run-physical-backup.sh` runs it inside the `postgres` container — the only
   place with the client tools, network reach, the WAL archive and the backup
   directory.
2. **`--format=tar --gzip` followed by `pg_verifybackup <dir>`.** On
   PostgreSQL 16 that reports *every* file as "present in the manifest but not
   on disk" and then fails on `pg_waldump`. The two lines contradicted each
   other. Tar verification arrives in PostgreSQL 17; until then the choice is
   a verifiable backup or a compressed one, and an unverified backup is not a
   backup. Plain also restores faster, which is what a base backup is *for*.
3. **The manifest digest was written inside the backup directory**, so every
   later verification reported `"backup_manifest.sha256" is present on disk
   but not in the manifest` on a perfectly good backup. It is now a sidecar
   beside the directory.

Also fixed: a failed run left its directory behind, looking exactly like a
recovery point in a listing and skewing the WAL retention that prunes against
the oldest base. It is now removed on failure and kept only once verified. And
it runs `--user postgres` rather than root.

---

## 4. The nightly script reported catastrophe on success

`BACKUP_ROOT` is a **container** path (`/backup/logical`) and was also used
for the host-side retention sweep, `mkdir` and `df`. The sweep therefore
searched a path that does not exist on the host, found nothing, computed
`REMAINING=0`, and ended every run on

> `FAILED: retention removed everything. This should be impossible.`

after a backup that had in fact succeeded. Host and container paths are now
separate variables. A guard that cries catastrophe on a healthy run teaches an
operator to ignore it.

---

## 5. Architecture now

```
            ROOT DISK  /dev/nvme0n1p1  38G, 49% used
              └── pgdata  (the live database)

            DATA VOLUME  /dev/nvme1n1  49G, 2% used   ← different device
              /var/lib/lacteva/
                ├── backup/logical/<stamp>/      31 backups, ~17MB each
                ├── backup/base/<stamp>/          1 base backup, ~950MB
                ├── backup/quarantine/            withdrawn artefacts
                └── wal-archive/                  9 segments, 97MB

            OFF-SITE  s3://lacteva-offsite-backups-590182060076 (ap-southeast-1)
              └── the logical backup, tar + manifest, checksum-verified
```

Backups and WAL are now **bind mounts** onto the dedicated volume rather than
Docker named volumes on the root disk. Both copies were compared
**byte-for-byte** before the old volumes were removed.

Effect on the root disk: **59% → 49%**, and the WAL archive fell from
**255 segments / 3.1 GB to 9 / 97 MB** once pruning ran against what the
retained base backups actually need.

---

## 6. Schedule, retention and validation

| Unit | When (UTC) | Proven by |
| --- | --- | --- |
| `lacteva-backup-nightly` | daily 02:15 | Real run: backup → verify → off-site → prune, all succeeded |
| `lacteva-backup-weekly` | Sun 03:30 | Real run: `backup successfully verified` |
| `lacteva-backup-verify` | Sat 05:00 | Real run: full restore drill, §7 |
| `lacteva-backup-watchdog` | 06:40, 14:40, 22:40 | Real run, and a forced failure, §8 |
| `lacteva-disk-guard` | every 6h | Reports the backup volume separately |

| Artefact | Retention | Enforced where |
| --- | --- | --- |
| Logical backups | 30 days | `run-logical-backup.sh`, only after a verified backup |
| Off-site copies | 30 | `backup.cli offsite-prune` — never below 1, never the newest |
| Base backups | 35 days | `pg-backup.sh` |
| WAL segments | Whatever the **oldest retained base** needs | `pg_archivecleanup` against the `.backup` label, never against a date |

Pruning always happens **after** success. The worst case is too many copies.
Both scripts refuse to finish if retention has left zero recovery points.

**Validation is separate from writing.** The engine checksums as it writes;
`backup.cli verify` re-reads those checksums from disk afterwards, which is a
different question and the one that matters after a bad sector. The nightly
run does both, then replicates off-site, and only then prunes.

---

## 7. The restore test

§5 asked for a restore into an isolated, non-production database. The existing
verifier restored into a scratch *database on the production server* — a real
boundary, but it puts the rehearsal and the thing being rehearsed for under
one postmaster. One wrong `LACTEVA_DATABASE_URL` and the drill is
indistinguishable from the accident.

It now starts a **separate throwaway PostgreSQL container** with its own
volume, restores into that, and removes both on every exit path including
failure — so a restored copy of live customer data never outlives the drill.
Production is read **only**, to count rows and sum money.

Three defects surfaced while making it run:

- **"Latest backup" was chosen by sorting names.** `predeploy-20260812T220548Z`
  sorts after `20260813T121038Z` because `p` > `2`, so the drill verified a
  pre-deployment backup from the previous day and never looked at the
  scheduled one. It now picks by modification time.
- The comparison query named `audit_log`; the table is `audit_record`.
- Host and container paths were conflated, as in §4.

### Result

Restored `20260813T121038Z` into an isolated server, applied migrations, ran
`integrity --deep` (which rebuilds every projection from the restored event
log, BR-0015) — then compared **per table**, because two tables wrong by +1
and −1 sum to the right answer:

| Table | Rows | | Table | Rows |
| --- | --- | --- | --- | --- |
| organization | 4 ✓ | | settlement | 56 ✓ |
| user_account | 79 ✓ | | payment | 29 ✓ |
| role | 12 ✓ | | receipt | 25 ✓ |
| user_role | 9 ✓ | | customer_invoice | 14 ✓ |
| customer | 16 ✓ | | customer_payment | 11 ✓ |
| supplier | 32 ✓ | | customer_receipt | 11 ✓ |
| collection_center | 7 ✓ | | milk_delivery | 570 ✓ |
| milk_collection_transaction | 359 ✓ | | audit_record | 5,461 ✓ |

And **the money**, because rows arriving says nothing about the values in them
surviving:

| Figure | Production = Restored |
| --- | --- |
| Deliveries | 472,874.00 |
| Invoiced | 466,674.00 |
| Invoice amount due | 466,674.00 |
| Customer payments | 254,713.00 |
| Customer receipts | 254,713.00 |
| Collections gross | 361,024.00 |
| Settlements gross / net | 247,486.00 |
| Supplier payments | 122,147.50 |
| Supplier receipts | 101,917.50 |

Sixteen of sixteen tables and ten of ten financial totals, exact. Whole drill:
**~60 seconds**.

---

## 8. Failure detection

Backups stop in two ways and they need different detection.

**A run fails.** Every backup unit now carries
`OnFailure=lacteva-backup-alert@%n.service`, which writes to the journal at
error priority and appends to `/var/log/lacteva/BACKUP-FAILED` with the
failing unit's status. It uses only what is already on the machine and always
exits 0 — an alerting path that can itself fail turns one problem into
silence.

**A run never happens.** Nothing fails, systemd is content, every dashboard is
green. *This is the state the platform was actually in*, and `OnFailure` would
never have fired once. `backup-watchdog.sh` asks from the outside, three times
a day, from two independent sources: the platform's own `backup.cli status`,
which knows whether a backup **verified** but needs the API up — and the API
being down is a perfectly good reason backups stopped — and the filesystem,
which does not care what is running. It also checks the timers are enabled
**and** active, which is the exact thing nobody was checking.

**And the rule that should have existed.** `core/alerts.py` had twelve rules
and none for backups, so the `backups` health component — red past 26 hours
since BAK-001 — was watched by nobody. `backups_stale` (critical) and
`backups_degraded` (warning) now read it, and because rules there drive both
the operator API and the exported Prometheus rules, one definition covers
both.

The chain was **demonstrated**: forcing the watchdog to fail produced
`NOT PROTECTED`, a non-zero exit, the `OnFailure` handler, an error-priority
journal line and the marker file. The test marker was then removed — a marker
recording a test is worse than no marker.

### How an operator checks

```bash
cat /var/log/lacteva/backup-status          # protected=yes
ls /var/log/lacteva/BACKUP-FAILED           # should NOT exist
systemctl list-timers 'lacteva-*'           # four backup timers scheduled
```

---

## 9. Disk safety

- Backups are on a **different device** from the database, so a full root disk
  cannot be relieved by deleting recovery points and a full backup volume
  cannot eat the database's headroom. The disk guard reports them separately
  and **deletes nothing** on the backup volume — retention belongs to the
  scripts, which know which copies are still needed.
- The guard exits non-zero if the backup volume passes 85%, because a backup
  that fails for want of space is how a bad night becomes unrecoverable.
- WAL is bounded by the oldest retained base backup, not by a date — the only
  safe rule, since anything newer may be needed to roll that base forward.
- The restore drill removes its server **and its volume** on every exit path.
- Docker images, build cache, stopped containers and old releases: unchanged
  from DEMO-010's guard.

Current: root **49%** (20 GB free), backup volume **2%** (46 GB free).

---

## 10. Security

- Backups and the WAL archive are `0700`, owned by uid 999 — the uid both
  PostgreSQL and the API run as. The physical backup runs `--user postgres`
  rather than root, so its files match.
- **No credential is in git.** `/etc/lacteva/.env.production` is root-owned
  `0600` and holds the database, S3 and application secrets. The example file
  carries names and explanations, never values.
- The drill server gets a **random password per run**, generated from
  `/dev/urandom` and never written to disk.
- The drill's data volume is destroyed on every exit path, including failure,
  so a restored copy of live customer data does not outlive the rehearsal.
- Off-site objects are checksum-verified on upload and on fetch.
- No credential is echoed by any script; `pg-backup.sh` receives `PGPASSWORD`
  through the environment, not the command line.

---

## 11. AWS changes and cost

**Nothing was created, resized or deleted. No recurring cost was added.**

| Change | Cost |
| --- | --- |
| Backups moved onto the already-provisioned EBS data volume | **$0** — the volume existed and was empty |
| Off-site S3 usage (existing bucket, existing credentials) | ~**$0.01/month** for ~500 MB under a 30-copy retention. Pre-existing, not introduced here |
| EC2 | Unchanged — `c7i-flex.large`, not resized |
| New services | **None** |

No RDS, no NAT gateway, no ECS/EKS, no managed backup service, no new
monitoring platform.

---

## 12. Verification

| § | Check | Result |
| --- | --- | --- |
| 11 | Backup creation | Nightly unit ran end to end: backup, verify, off-site, prune |
| 11 | Backup validation | `backup.cli verify` re-read checksums from disk; `pg_verifybackup` clean |
| 11 | Isolated restore | Separate throwaway server, §7 |
| 11 | Restored-data verification | 16/16 tables, 10/10 money figures exact |
| 11 | Retention | Logical 31 retained / 0 pruned; WAL 255 → 9 against the oldest base |
| 11 | Cleanup | Drill server and volume removed; quarantine used instead of deletion |
| 11 | Disk safety | Root 59% → 49%; backup volume reported separately, 85% threshold |
| 11 | Service recovery | `lacteva.service` installed, adopted the running stack, `active` |
| 13.1–3 | Application, login, dashboard | 96 collections · 90 deliveries · 211,961.00 owed |
| 13.4 | Customer workflow | 16 customers · 14 bills · 11 receipts |
| 13.5 | Supplier workflow | 24 suppliers · 52 settlements · 21 receipts |
| 13.6 | Database connectivity | Receivables report answered, 7 owing |
| 13.7 | Backup exists | 31 logical, 1 base, off-site current |
| 13.8–9 | Restore succeeded and verified | §7 |
| 13.10 | Production data unchanged | Counts and money identical to the pre-drill snapshot |
| 13.11 | Disk healthy | Root 49%, backup volume 2% |

One thing broke during the work and was fixed: recreating **some** containers
(`compose up -d postgres`) left nginx resolving a stale address — the
documented PILOT-F03 trap — returning 502 on `/health/ready` while the API was
healthy. Restarting nginx fixed it, which is what `deploy.sh` does
automatically and what I skipped by driving compose directly.

A **full** stop/start does not have this problem, and that was verified rather
than assumed: `systemctl stop lacteva.service` took the stack to 0 containers,
`systemctl start` returned all 11, and `/health/ready` answered 200 on the
first attempt with no manual step. nginx starts last, after the API and portal
are healthy, so it resolves fresh addresses.

### Tests

```
backend      1,314 tests — 1,240 passed, 74 skipped (PostgreSQL-only), 0 failed
ruff check + ruff format --check      clean (226 files)
validate_docs.py                      174 files, all checks passed
```

Focused suites were used during development, as §11 asked; the full regression
ran once at the milestone.

---

## 13. Known limitations

1. **One host.** Losing the instance loses the database, both local backup
   copies and the WAL archive. The only survivor is the nightly logical backup
   in S3, so a total-loss recovery is to the **last nightly** and PITR is gone
   with the machine. That is the honest limit of this topology.
2. **The database is still on the root disk.** Moving `pgdata` to the
   dedicated volume needs a maintenance window and carries real risk if
   interrupted, so it is recommended rather than done — see §14.
3. **WAL is not replicated off-site**, so the ~1-minute RPO that
   `archive_timeout=60` provides only holds while the instance survives.
4. **The physical backup is uncompressed** (§3). ~950 MB per weekly backup
   against 46 GB free; revisit on PostgreSQL 17, where tar can be verified.
5. **The restore drill compares counts and sums, not row-by-row content.** A
   corruption that preserved every count and total would pass. `integrity
   --deep` covers the business rules that matter, but this is not a
   byte-for-byte comparison.
6. **No alert reaches a human off the machine.** Failures land in the journal,
   a marker file and Prometheus. Wiring `backups_stale` to email or SMS needs
   an Alertmanager route that does not exist yet.
7. **The off-site bucket has no lifecycle policy or object lock.** Retention
   is applied by the platform; nothing at the bucket prevents a credential
   with delete rights from removing every copy.

---

## 14. Recommended next

1. **Move `pgdata` to the dedicated volume.** It is the last piece still on
   the root disk, and the disk that filled twice. Needs a window: stop the
   stack, `cp -a` the data directory, verify, repoint, start. Roughly 15
   minutes for 950 MB, and it removes the whole class of root-disk incidents.
2. **Object lock or versioning on the off-site bucket**, so the last copy
   cannot be deleted by a compromised credential. Pennies.
3. **Replicate WAL off-site**, which turns the total-loss RPO from 24 hours
   into minutes. `archive-wal.sh` is the natural place — it already owns the
   atomic write.
4. **An Alertmanager route** so `backups_stale` reaches a person rather than a
   dashboard.
5. **A second host, or at minimum a documented AMI + volume snapshot
   schedule**, so §13.1 stops being true. EBS snapshots are cheap and would
   give a rebuildable machine rather than a rebuildable database.
6. **DEMO-012 — Mobile applications**, the roadmap item DEMO-011 displaced.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-13 | DEMO-011: made every documented backup guarantee actually execute, and fixed the seven ways they could not have. |
