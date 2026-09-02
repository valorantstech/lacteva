---
id: INFRASTRUCTURE
title: Production Infrastructure
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-06
last-updated: 2026-08-06
related: [DEPLOYMENT, BACKUP, RESTORE, DISASTER_RECOVERY, SECURITY, RUNNING]
baseline: ARCH-BASELINE-V1
---

# Production Infrastructure

Provisioning a Lacteva production environment from zero. Established by **INF-001**.

[DEPLOYMENT.md](DEPLOYMENT.md) covers what happens *on* a host. This covers how the host comes to exist, how it is replaced, and what to do when it is gone.

> **Honest limit, stated once.** No Terraform binary, cloud account, or host exists in the environment where this was written. Nothing here has been applied. The configurations were validated by structural review and a test suite that asserts their contents — `terraform plan` has never run. **Treat the first plan as a review step, not a formality**, and expect to correct something.

---

## 1. Topology

One machine. That is not a first draft — the platform is a modular monolith with a single PostgreSQL database, so a single host is the honest shape for it. Scaling out means changing the platform's architecture, not this directory (§5).

```
                    ┌─────────────────────────────┐
   Internet ──80/443─┤ static IP (survives rebuild) │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  cloud firewall (outside)   │  80, 443, SSH-from-known-ranges
                    └──────────────┬──────────────┘
                    ┌──────────────▼──────────────┐
                    │  host: ufw + fail2ban       │  second layer
                    │                             │
                    │  nginx ─┬─ marketing      │  compose network,
                    │         ├─ portal         │  only nginx publishes
                    │         └─ api ── postgres│
                    │                   redis   │
                    │            prometheus     │
                    │            grafana loki   │
                    └──────────────┬──────────────┘
                    ┌──────────────▼──────────────┐
                    │  data volume (separate)     │  /var/lib/lacteva, /backup
                    └─────────────────────────────┘
```

**Four names, one address** (WO-63 / D-20). nginx decides by `Host`:
`lacteva.com` and `www` reach the marketing site; `app.lacteva.com` the admin
portal; `api.lacteva.com` the API, which is what the mobile app is built
against; and `dev.phoenixsoft.in` keeps serving portal-and-API for the
handsets that were built before those names existed. Anything else is refused
with 421 by an explicit default server rather than being handed whichever site
nginx parsed first. One Let's Encrypt certificate covers all five.

The **static IP and the data volume outlive the machine**. That is what makes host replacement routine rather than a recovery: build a new server, attach both, deploy. DNS never changes, so there is no propagation wait and no certificate reissue.

### Supported targets

| Target | Status | Where |
| --- | --- | --- |
| **Hetzner Cloud** | Primary | `infra/terraform/hetzner` |
| **AWS** | Optional abstraction, thin by design | `infra/terraform/aws` |
| **Local Docker** | Development and the proof stack | `docker-compose.yml`, `docker-compose.proof.yml` |

The AWS path exists because the topology is portable, not because two production targets are being maintained in parallel — two half-maintained definitions are worse than one maintained one, and the second is always the one nobody has applied since March. `infra/terraform/aws/README.md` says what it deliberately omits (RDS, VPC creation, load balancers) and why.

Everything above the machine — cloud-init, the filesystem standard, systemd, `deploy.sh` — is **shared unchanged** between them.

---

## 2. Filesystem standard

| Path | Holds | Survives host replacement? |
| --- | --- | --- |
| `/opt/lacteva/releases/<tag>/` | One directory per deployed release | No — rebuilt by deploy |
| `/opt/lacteva/current` | Symlink to the live release. **Rollback re-points it** | No |
| `/etc/lacteva/` | `.env.production`, `secrets/`. Root-only, `0700` | No — restored from the secret store |
| `/var/lib/lacteva/` | PostgreSQL, Redis, Prometheus, Loki, Grafana | **Yes** — the data volume |
| `/var/log/lacteva/` | Host-written logs: deploys, backups, verification | Yes |
| `/backup/` | `logical/`, `base/`, `wal/` — symlinked onto the volume | **Yes** |

The rule: **anything that must survive is on the volume**. `/opt` and `/etc` are reproducible from provisioning and the secret store, which is what makes the host disposable.

---

## 3. Provisioning

```bash
cd infra/terraform/hetzner
cp terraform.tfvars.example terraform.tfvars   # git-ignored
export HCLOUD_TOKEN=...                        # never in a file

terraform init
terraform plan      # read it. Especially the first time
terraform apply
```

Then, in order:

1. **DNS** — point A and AAAA at the outputs. The IP is stable, so this is the only time.
2. **Wait for cloud-init** — `ssh lacteva@<ip> 'cloud-init status --wait'`. It installs Docker, formats and mounts the volume, builds the filesystem standard, hardens SSH, configures ufw + fail2ban + chrony + logrotate, and enables unattended security updates.
3. **Configuration** — copy `.env.production` to `/etc/lacteva/` as root, mode `0600`.
4. **TLS** — issue certificates into `TLS_CERT_DIR`.
5. **systemd** — `sudo cp infra/systemd/* /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now lacteva.service lacteva-backup-nightly.timer lacteva-backup-weekly.timer lacteva-backup-verify.timer`
6. **Deploy** — `/opt/lacteva/current/infra/deploy/deploy.sh <tag>`

**Provisioning installs nothing application-shaped, and deployment provisions nothing.** Keeping them separate is why a host can be replaced without a deploy and redeployed without a rebuild.

### What cloud-init deliberately does not do

- **It does not reformat a volume that already has a filesystem.** A re-run on a rebuilt image must never touch a volume holding production data.
- **It does not reboot for updates.** Security patches install automatically; the reboot is a scheduled maintenance task (§7), because rebooting a single-host platform without warning is an unplanned outage.

---

## 4. Deployment

```bash
./infra/deploy/deploy.sh v1.4.2        # pull → backup → migrate → up → verify → smoke
./infra/deploy/deploy.sh --rollback    # back to the previous release
```

Six steps, and **automatic rollback on failure** — the alternative is a half-deployed platform sitting broken until somebody notices and decides.

| Step | If it fails |
| --- | --- |
| 1. Pull the image | Nothing has changed. The old version is still serving |
| 2. Pre-deployment backup | Refuses to continue. This is the last cheap moment to get a way back |
| 3. Stage the release | — |
| 4. Migrate | Tag reverted, old version still running, schema unchanged |
| 5. Start + verify | Rolled back automatically |
| 6. Smoke test | Rolled back automatically |

**The schema is never rolled back automatically.** A code rollback is safe when the migration was expand-only and unsafe when it contracted, and no script can tell from the outside. `deploy.sh` reports when the schema moved and points at [DEPLOYMENT.md §5](DEPLOYMENT.md) for the compatibility matrix. `--no-rollback` keeps a broken deployment for inspection.

---

## 5. Scaling

The order in which this topology runs out, so the next work order is chosen by evidence rather than by guess:

| # | What binds first | Symptom | The move |
| --- | --- | --- | --- |
| 1 | **Disk** | The data volume fills; backups stop first, because they are the largest writer | Grow the volume online. Then implement retention and partitioning — DBD-0001 models ~12 TB/year at full scale, which nothing here addresses |
| 2 | **PostgreSQL I/O** | Autovacuum falls behind; queries slow at the same row counts | Move PostgreSQL to managed (RDS/Aurora), which also brings failover and PITR |
| 3 | **CPU under consumer load** | Outbox lag grows and never returns to zero | Split the background workers onto their own host — they already share nothing with the API but the database |
| 4 | **API concurrency** | Latency rises with request rate while CPU is idle | More `API_WORKERS`, then more hosts behind a load balancer. Needs the shared-nothing check below |

**What blocks horizontal scaling today:** nothing in the API holds state between requests, but the relay dispatcher, consumer runner and health sampler are per-process loops. Running two API hosts would run two of each — the outbox uses CAS dispatch and consumers use an idempotency ledger, so this is *safe*, but it doubles the polling load and has never been tested. Treat "run the workers on exactly one host" as a constraint until it is.

---

## 6. Secrets

Three mechanisms, in increasing order of safety:

1. **`/etc/lacteva/.env.production`** — root-owned, `0700` directory, `0600` file. Read by compose. Visible to `docker inspect` and to any child process's environment.
2. **Docker Secrets** — `/run/secrets/<name>`, read by pydantic-settings' `secrets_dir`. A file named `lacteva_jwt_keys` sets `LACTEVA_JWT_KEYS` without it appearing in an environment block. **Use this for anything that signs or decrypts.**
3. **Terraform variables** — `HCLOUD_TOKEN` exported, never written to a file. `terraform.tfvars` is git-ignored.

### Rotation

| Secret | Procedure | Downtime |
| --- | --- | --- |
| **JWT signing key** | **Additive.** Add the new key as `current`, leave the old as `retiring` until every issued token has expired (`LACTEVA_JWT_ACCESS_TTL_SECONDS`), then remove it. [JWT-ROTATION](docs/03-architecture/05-security/JWT-ROTATION.md) | None |
| **PostgreSQL password** | `ALTER USER … PASSWORD`, update `.env.production`, `systemctl reload lacteva` | Brief connection churn |
| **Redis password** | Update both, restart redis and api. The limiter fails open, so requests continue | None functionally |
| **Hetzner / AWS token** | Rotate in the provider console, re-export. Affects Terraform only | None |
| **TLS certificate** | Reissue into `TLS_CERT_DIR`, `docker compose exec nginx nginx -s reload` | None |
| **SSH keys** | `terraform apply` with the new map, confirm access, **then** remove the old key | None |

The rule for all of them: **add the new one, confirm it works, remove the old one.** Never the other way round — a rotation that starts by revoking is a rotation that can lock you out.

### The SSH allow-list

Port 22 is restricted to individual `/32` addresses, and an operator's address is **dynamic** — it changes with the network they are on. Following the rule above means a new address is added before the old one stops working, so the list accumulates addresses nobody uses any more. Each one is a standing invitation to whoever holds that address next.

So the second half of the rule needs doing, not just the first. Before removing an entry, check that it is genuinely stale:

```bash
# who is connected right now
sudo ss -tnp state established '( sport = :22 )'
# when each source last authenticated successfully
sudo zgrep -h sshd /var/log/auth.log* | grep Accepted | grep " <ip> " | tail -1
# nothing else in the account references it
aws ec2 describe-security-groups --filters "Name=ip-permission.cidr,Values=<ip>/32"
```

Then revoke **that one range**, by naming it explicitly — never by rewriting the port-22 permission, which would take the working address with it:

```bash
aws ec2 revoke-security-group-ingress --group-id <sg> \
  --ip-permissions '[{"IpProtocol":"tcp","FromPort":22,"ToPort":22,
                      "IpRanges":[{"CidrIp":"<ip>/32"}]}]'
```

**Nothing automated depends on this list.** CI builds images and pushes them to ECR over OIDC and never touches the host; the host pulls. Monitoring is Prometheus and Grafana in containers on the machine, and nginx already restricts `/metrics` to internal ranges. The only consumer is a human running `deploy.sh`.

**The way back in, if the list is ever wrong: SSM.** Session Manager works over the instance's outbound connection and does not consult inbound rules at all, so it survives any mistake made here — including revoking the address you are sitting on. `aws ssm describe-instance-information` should always show this instance `Online`; if it does not, fix that before touching port 22.

Removed so far: `122.170.193.69/32` (superseded 2026-08-11) and `223.236.99.188/32` (superseded 2026-08-13, removed after DEMO-012 — last successful login 2026-08-12T22:05Z, no session since, referenced by nothing else in the account).

---

## 7. Maintenance

| Task | Cadence | Notes |
| --- | --- | --- |
| Build images | On push, on GitHub | `.github/workflows/images.yml` → ECR. **Never on this host** — see DEPLOYMENT.md §3 |
| Security patches | Automatic | `unattended-upgrades`, security origin only |
| **Reboot for a kernel update** | Monthly, scheduled | Deliberately manual. `systemctl reboot`; systemd brings the stack back |
| Verify backups | Weekly, automatic | `lacteva-backup-verify.timer` — restores into a scratch database and runs deep integrity |
| Reclaim disk | Every 6 hours, automatic | `lacteva-disk-guard.timer` → `infra/deploy/disk-guard.sh`. Does nothing below 75%; above it, reclaims build cache, dangling images, stopped containers and old release directories, stopping at 60%. Exits non-zero — a real alert — if it is still above 90% after everything safe was tried |
| Check disk | Weekly | The guard above does the reclaiming; this is the human look at whether the *data* is what is growing. The volume filling is failure #1 in §5 |
| Review the security posture | Quarterly | [SECURITY-CHECKLIST](docs/03-architecture/05-security/SECURITY-CHECKLIST.md) |
| Rotate the signing key | Quarterly, or on suspicion | §6 |

---

## 8. Server replacement

The routine operation this topology is built for. Roughly 20 minutes, no DNS change, no certificate reissue.

1. `systemctl stop lacteva` on the old host — drains requests, then background workers (DEPLOYMENT.md §7).
2. Take a final logical backup and confirm it verifies.
3. `terraform taint hcloud_server.app && terraform apply` — the IP and volume have `prevent_destroy` and are re-attached to the new machine.
4. `cloud-init status --wait`. It will **not** reformat the volume: it already has a filesystem.
5. Restore `/etc/lacteva/` from the secret store.
6. Install the systemd units and `deploy.sh <tag>`.
7. `verify-deployment.sh` and the smoke test.

**The volume carries the database across.** Nothing is restored from backup in the normal case — the backup exists for the case where step 3 goes wrong.

---

## 9. Disaster recovery

[DISASTER_RECOVERY](docs/03-architecture/06-operations/DISASTER_RECOVERY.md) names the disasters. What this infrastructure adds:

| Loss | Recovery | Data lost |
| --- | --- | --- |
| The container | Docker restarts it | None |
| The host | §8, volume intact | None |
| **The volume** | New volume, restore the newest verified logical backup | **Up to 24 hours** |
| The whole project/region | Rebuild elsewhere from off-site backups | Up to 24 hours, **if backups are off-site** |

Three things must be said plainly rather than implied:

- **Backups live on the same volume as the database.** Losing the volume loses both. Provider snapshots (Hetzner server backups / AWS Backup) are the independent copy, and they are the *only* thing standing between the platform and total loss. **Shipping logical backups off-host is the single highest-value gap in this infrastructure.**
- **WAL archiving is on** (PITR-001), so point-in-time recovery is available and proven — see [PITR](docs/03-architecture/06-operations/PITR.md). It was previously absent: `wal_level=replica` was set and `archive_mode` was not, which meant no WAL left the server and the documented 5-minute RPO was unachievable. The RPO is now bounded by `archive_timeout` (60s by default) rather than by the age of the last logical backup.
- **The WAL archive is a local volume.** Archiving to object storage, and replicating the archive off-host, is not yet done — so a total host loss still falls back to the logical backup.
- **There is no failover.** Recovery is a deliberate human decision, and on a single host it is a multi-hour outage.

---

## 10. Production readiness checklist

Before the first real tenant. Each line is a question with a yes/no answer.

### Capacity
- [ ] **CPU** — ≥8 vCPU (cpx41 / m6i.2xlarge). The whole stack shares one machine
- [ ] **Memory** — ≥16 GB. `shared_buffers` 512 MB + `maintenance_work_mem` 1 GB + API workers + monitoring
- [ ] **Disk** — data volume ≥200 GB, and `df` checked against §5 failure #1
- [ ] `POSTGRES_MAX_CONNECTIONS` > `API_WORKERS × (pool_size + max_overflow)` + workers + operator headroom

### Network and identity
- [ ] **DNS** — A and AAAA at the static IP; reverse DNS set
- [ ] **TLS** — certificate valid, renewal automated and *tested*, HSTS decided deliberately (close to irreversible)
- [ ] **Firewall** — 80/443 open; SSH restricted to known ranges; the plan refuses `0.0.0.0/0`
- [ ] SSH: password auth off, root login off, fail2ban running

### Platform
- [ ] **PostgreSQL** — reachable, migrations at head, **RLS enabled and FORCED on every tenant table** (`verify-deployment.sh` checks this)
- [ ] **Redis** — password set, `maxmemory` set, rate limiting live
- [ ] `LACTEVA_ENV=prod` — the platform refuses to start on a development credential
- [ ] JWT keys are RS256, from a secret rather than an env file
- [ ] `LACTEVA_CORS_ORIGINS` is an exact list, not a wildcard

### Operations
- [ ] **Monitoring** — Prometheus scraping, Grafana reachable, alert rules loaded, Loki receiving
- [ ] Someone receives the alerts. An alert nobody sees is a dashboard
- [ ] **Backups** — nightly timer enabled, one has run, one has been **verified by restore**
- [ ] Backups are copied **off-host** (§9 — currently the largest gap)
- [ ] `systemctl is-enabled lacteva` → enabled. The platform survives a reboot
- [ ] `deploy.sh --rollback` has been *rehearsed*, not just read

### Known gaps — acknowledge rather than tick
- [ ] **SMTP** — not wired. NOT-001 ships logging and placeholder providers; no email leaves the platform
- [ ] **SMS** — wired (MSG-001). Gateway URL, key (prefer a Docker secret) and sender id set; **proven in `dry_run` on staging before `http` in production**, because a wrong sender id is a permanent rejection and suppliers would silently stop being told they were paid
- [x] **PITR** — available and proven (§9, [PITR](docs/03-architecture/06-operations/PITR.md))
- [ ] **PII is stored in the clear**, with no erasure path (ABR-002 D-2)

---

## 11. What this infrastructure does not do

- No high availability, no failover, no read replica
- No off-site backup replication (§9)
- No off-host WAL archive (PITR itself works; the archive is local)
- No horizontal scaling (§5)
- No secret manager — secrets are files on the host
- No CDN, no WAF beyond nginx's rate limiting
- No infrastructure CI: `terraform plan` is run by a person, deliberately, because a pipeline that can `apply` unattended can also destroy unattended

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by INF-001. |
