---
id: DEPLOYMENT
title: Production Deployment
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-06
last-updated: 2026-08-06
related: [BACKUP, RESTORE, DISASTER_RECOVERY, POSTGRES-PROOF, SECURITY, RUNNING]
baseline: ARCH-BASELINE-V1
---

# Deployment

How Lacteva goes to production, comes back from a bad deploy, and survives losing its database. Established by **DEP-001**.

This document is operational. It assumes the platform's guarantees rather than explaining them — for *why* row-level security or the backup format works the way it does, follow the links.

> **Honest limit, stated once.** None of this has been executed. There is no Docker, PostgreSQL, or production host in the environment where it was written; the compose files, nginx configuration, and scripts were validated by parsing, static analysis, dry-run against stubs, and a test suite that asserts their contents. **The first real deployment is the first execution.** Treat §12 as a first-run checklist rather than a troubleshooting section, and expect to correct something.

---

## 1. What the stack is

Ten containers, one published port.

| Service | Purpose | Reachable from outside? |
| --- | --- | --- |
| `nginx` | TLS termination, compression, rate limiting, the only front door | **Yes** — 80/443 |
| `api` | The platform. Uvicorn, N workers | No |
| `migrate` | One-shot: `alembic upgrade head`, then exits | No |
| `postgres` | The database | No |
| `redis` | Rate-limit counters | No |
| `prometheus` | Metric storage, alert rules | No |
| `grafana` | Dashboards | No |
| `loki` | Log storage | No |
| `promtail` | Ships container logs to Loki | No |
| `dockerproxy` | A read-only, single-endpoint view of the Docker API for promtail | No |

**Why `dockerproxy` exists.** Promtail needs container metadata to label logs by service, and the usual way to get it is to mount `/var/run/docker.sock`. That hands a *log shipper* the ability to start privileged containers — the Docker API is root on the host, and `:ro` on a unix socket restricts nothing about the calls made through it. The proxy exposes one endpoint family and refuses the rest, so a compromised promtail can list containers and nothing else.

Everything but nginx uses `expose:` rather than `ports:`. Reaching the database means being on the compose network or opening a tunnel — a decision someone makes, not a port someone forgets.

---

## 1b. Where the host comes from

This document assumes a provisioned host. [INFRASTRUCTURE.md](INFRASTRUCTURE.md) is how one comes to exist — Terraform for the machine, static IP, volume and firewall; cloud-init for Docker, the filesystem standard and hardening; systemd for start-on-boot and the backup timers.

Provisioning installs nothing application-shaped, and deployment provisions nothing. That separation is why a host can be replaced without a deploy and redeployed without a rebuild.

## 2. Before the first deployment

```bash
cp .env.production.example .env.production
```

Then fill it in. Every variable is documented in the template; the ones that will stop the deploy if wrong:

- **`LACTEVA_IMAGE_TAG`** — a git SHA, never `:latest`. Compose refuses to start without it. This is also the only thing a rollback changes.
- **`LACTEVA_ENV=prod`** — turns on the production posture *and* the refusal to start on a development credential. The platform will not boot with the sample JWT secret.
- **`LACTEVA_JWT_KEYS`** — the RS256 key registry. Prefer a Docker Secret (§10).
- **`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`** — generate them: `openssl rand -base64 36`.
- **`LACTEVA_CORS_ORIGINS`** — a JSON list of exact origins. Never a wildcard.

Put `fullchain.pem` and `privkey.pem` in `TLS_CERT_DIR`. To terminate TLS at a load balancer instead, point traffic at port 80 and remove the redirect block from `infra/nginx/conf.d/lacteva.conf`.

**Sanity check before you start anything:**

```bash
docker compose -f docker-compose.production.yml --env-file .env.production config >/dev/null
```

That resolves every variable and fails loudly on a missing one — cheaper than discovering it half-started.

---

## 3. Deploying

```bash
export TAG=$(git rev-parse --short HEAD)
docker build -t lacteva/platform-core:$TAG services/platform-core

sed -i "s/^LACTEVA_IMAGE_TAG=.*/LACTEVA_IMAGE_TAG=$TAG/" .env.production

docker compose -f docker-compose.production.yml --env-file .env.production up -d

./infra/deploy/verify-deployment.sh
./infra/deploy/smoke-test.py --base-url https://api.example.com
```

**What happens in `up -d`, in order.** Nothing waits on a timer:

1. `postgres` and `redis` start. Compose waits for their health checks — `pg_isready` and a `PING` that must answer `PONG`.
2. `migrate` runs `alembic upgrade head` and exits. **A failure here stops the deployment**: `restart: "no"` means it does not retry, so the API's `service_completed_successfully` condition never fires and nothing serves traffic against a schema that did not apply.
3. `api` starts, and is *healthy* only once `/health/ready` returns 200 — which now means every probe is non-critical, not merely that the database answered (§6).
4. `nginx` starts once the API is healthy, and publishes the port.

A sleep anywhere in that chain would be a guess: too short and it fails under load, too long and it taxes every deploy forever. `tests/test_deployment.py::test_nothing_in_production_waits_on_a_sleep` keeps it that way.

### Zero-downtime deploys

Compose alone cannot do them — `up -d` stops the old API container before starting the new one. Two options:

- **Accept a gap.** The API drains in-flight requests first (§7), so nothing is lost; requests during the swap get a 502 from nginx. For a single-region dairy platform with a maintenance window, this is a legitimate choice.
- **Run two stacks behind the load balancer** and shift traffic. That is beyond compose and belongs with the orchestrator work in §14.

State the choice; do not discover it during a deploy.

---

## 4. Upgrading

Same as deploying, plus one question answered **before** you start: *is the new schema backwards compatible with the running code?*

It has to be, because for the window between step 2 and step 3 above, the **new schema is live and the old code is still serving**. This is why migrations follow expand → backfill → contract:

| Phase | Migration does | Safe because |
| --- | --- | --- |
| **Expand** | Add nullable columns, new tables, `NOT VALID` constraints, `CREATE INDEX CONCURRENTLY` | Old code ignores what it does not know about |
| **Backfill** | Populate the new shape in batches | Both shapes are readable |
| **Contract** | Drop the old column, promote the constraint | Only after every deployed version writes the new shape |

**Never put expand and contract in the same release.** A migration that drops a column the running code still reads takes the platform down between step 2 and step 3, and the rollback in §5 will not save you — see the warning there.

---

## 5. Rollback

```
Deployment N  →  fails verification  →  rollback to N-1
```

**The rollback itself:**

```bash
sed -i "s/^LACTEVA_IMAGE_TAG=.*/LACTEVA_IMAGE_TAG=$PREVIOUS_TAG/" .env.production
docker compose -f docker-compose.production.yml --env-file .env.production up -d api nginx
./infra/deploy/verify-deployment.sh
```

Note what is **not** in that command: `migrate`. Rolling the code back does not roll the schema back, and it must not try to.

### Database compatibility — the part that decides whether rollback works

| Release contained | Roll back the code? | Roll back the schema? |
| --- | --- | --- |
| No migration | Yes, freely | Nothing to do |
| **Expand only** (new nullable column, new table, new index) | **Yes** — N-1 ignores what it does not use | **No.** Leave it. It is inert |
| **Backfill only** | Yes | No |
| **Contract** (dropped column, tightened constraint) | **No — not by rolling back** | See below |

**A contract migration makes code rollback unsafe**, because N-1 reads something that no longer exists. There are two honest options and neither is "run `alembic downgrade`":

1. **Roll forward.** Fix the defect and deploy N+1. Almost always right, and the reason contract migrations should ship in their own release, well after the expand that preceded them.
2. **Restore from backup.** Only if the data is also wrong. This loses everything written since the backup — see §8, and make the decision explicitly rather than reflexively.

`alembic downgrade` exists and every migration in the chain has a tested `downgrade()`, but a downgrade on a live production database **drops columns containing data written since the upgrade**. It is a development and test tool. If you are about to run it in production, take a backup first and understand that you are choosing to lose the delta.

### Rollback decision, in order

1. `./infra/deploy/verify-deployment.sh` fails → roll back the image now, investigate after. A half-serving deployment is worse than the previous one.
2. Verification passes but `smoke-test.py` fails → the platform is serving but the business path is broken. Same decision.
3. Both pass and something is still wrong → do **not** roll back reflexively. Check the dashboards ([OBSERVABILITY](docs/03-architecture/06-operations/OBSERVABILITY.md)) — a lagging consumer is a degraded platform, not a failed deploy, and rolling back will not fix it.

---

## 6. The health model

Three endpoints, three different questions. Confusing them is how a database outage becomes a restart storm.

| Endpoint | Question | Consulted by | On failure |
| --- | --- | --- | --- |
| `/health/live` | Is this process alive? | Container restart policy | Container is restarted |
| `/health/ready` | Should this instance get traffic? | nginx upstream, the container health check | Removed from the pool |
| `/v1/_ops/health` | What exactly is wrong? | Operators, Prometheus | Nothing automatic |

**Liveness touches nothing.** If it consulted the database, a database outage would make every orchestrator restart every container — an outage plus a thundering herd.

**Readiness aggregates all nine probes** — database, redis, outbox, consumers, projections, notifications, jwt_keys, background_workers, backups. Before DEP-001 it was a `SELECT 1`, which meant a load balancer was told an instance was ready while its consumer loop was dead and nothing downstream was happening. That is this platform's most dangerous failure shape, because it looks healthy.

**Degraded is still ready.** Only `critical` removes an instance from the pool. Taking a degraded instance out of rotation turns a partial problem into a total one, and there is nowhere better for the traffic to go.

Readiness answers from the background sampler's most recent evaluation rather than running nine probes per poll — a health check that is itself a load source is how a wobble becomes an outage. During the startup window, before the first sample, it falls back to a cheap database check.

---

## 7. Graceful shutdown

`SIGTERM` (a deploy, a restart, `docker compose down`) unwinds in a fixed order:

1. **Uvicorn stops accepting** connections and drains in-flight requests, up to `API_GRACEFUL_TIMEOUT` (30s).
2. **The lifespan shutdown runs.** Background workers — relay dispatcher, consumer runner, health sampler — are asked to stop. Each finishes the unit of work it is in, commits, and exits at its next sleep. They get `LACTEVA_SHUTDOWN_GRACE_SECONDS` (20s).
3. **Stragglers are cancelled.** A shutdown that can hang is not a shutdown. The log line says `workers_forced` and names them.
4. **The database engine is disposed** — last, and only after the loops are done, because disposing it while a consumer holds a session turns a clean shutdown into a stack trace.

`stop_grace_period: 90s` on the API container must exceed 30 + 20 with room to spare, or Docker kills the container mid-drain and the drain was pointless. `tests/test_deployment.py::test_the_api_container_gets_longer_to_stop_than_its_workers_get_to_drain` asserts the relationship.

**Why cooperative rather than cancellation.** Cancelling a consumer mid-transaction is *safe* — it rolls back and the event is retried, which the framework guarantees. But safe is not the same as clean: every rolling deploy would leave work to redo, and on a busy platform that is a lot of redoing. The `shutdown_complete` log line reports `drained` or `cancelled_after_grace` per worker, because the difference predicts whether the next start has work to catch up on.

---

## 8. Backup and restore

Full detail: [BACKUP](docs/03-architecture/06-operations/BACKUP.md), [RESTORE](docs/03-architecture/06-operations/RESTORE.md), [RECOVERY_CHECKLIST](docs/03-architecture/06-operations/RECOVERY_CHECKLIST.md). The deployment-specific parts:

```bash
# Take one
docker compose -f docker-compose.production.yml --env-file .env.production \
  exec api python -m platform_core.core.backup.cli backup /var/backups/$(date +%F)

# Verify it — a backup that has not been verified is a hope
docker compose ... exec api python -m platform_core.core.backup.cli verify /var/backups/2026-08-06

# Is the platform protected right now?
docker compose ... exec api python -m platform_core.core.backup.cli status
```

**Restore is CLI-only and always will be.** Overwriting the database is the most destructive operation the platform can perform, and an HTTP endpoint puts it one misrouted request away. The CLI requires being on the host, holding the credentials, and having typed the word.

A restore that loads every row but leaves the business wrong is a **failed** restore, and the command exits non-zero to say so (BR-0025).

**Scale limit, stated plainly:** the logical backup reads every row into JSONL. At the volumes DBD-0001 models, this is a portability and verification mechanism, not a four-hour recovery mechanism. Physical `pg_basebackup` + WAL is scripted in `infra/backup/` and **has never been executed** — that is the largest gap between documented and actual capability in this platform.

---

## 9. Disaster recovery

[DISASTER_RECOVERY](docs/03-architecture/06-operations/DISASTER_RECOVERY.md) names the disasters and their RPO/RTO. Two things a deployer must know:

- **There is no automated failover.** Recovery is a deliberate human decision, by design at this stage. At scale it is a multi-hour outage and should be replaced with managed failover (RDS Multi-AZ / Aurora) rather than something built here.
- **The documented 5-minute RPO is not currently achievable.** It assumes WAL archiving, which is scripted but not running. Until `archive_command` is configured and a point-in-time restore has actually been performed, the real RPO is *the age of the last logical backup*.

Do not let the second one sit in a document. It is the difference between losing five minutes and losing a day.

---

## 10. Secrets

Two mechanisms, in increasing order of safety:

**Environment file** — `.env.production`, read by compose. Simple. The value is visible to `docker inspect`, to `/proc/<pid>/environ`, and to any child process.

**Docker Secrets** — mounted at `/run/secrets/<name>` and read by pydantic-settings' `secrets_dir`. A file named `lacteva_jwt_keys` sets `LACTEVA_JWT_KEYS` without it ever appearing in an environment block:

```bash
docker secret create lacteva_jwt_keys ./keys.json
```

Then add to the `api` and `migrate` services:

```yaml
    secrets: [lacteva_jwt_keys]
secrets:
  lacteva_jwt_keys:
    external: true
```

**Use secrets for anything that signs or decrypts** — the JWT registry above all. A private signing key in an env file is a private signing key in every crash dump.

**Rules that are not negotiable:**

- `.env.production` is git-ignored; `.env.production.example` is committed and contains only placeholders. A test asserts the second part.
- The platform **refuses to start** in `prod` on a development credential. That is a startup failure, not a warning.
- Rotating the signing key is additive: add the new key as `current`, leave the old as `retiring` until every issued token has expired, then remove it. [JWT-ROTATION](docs/03-architecture/05-security/JWT-ROTATION.md).

---

## 11. Version upgrades

**PostgreSQL major version.** The verification workflow covers 16 and 17, so both are known to work with the schema and the policies. A major upgrade is still a dump/restore or `pg_upgrade` — not a change to `POSTGRES_VERSION` on a running volume, which will refuse to start against a data directory from another major version. Sequence: back up, verify the backup, stop the stack, upgrade, restore, run `verify-deployment.sh`, run the smoke test.

**Redis, nginx, Prometheus, Grafana, Loki.** All pinned to a minor version. Bump one at a time and re-run verification; a nightly PostgreSQL Verification run will catch a base-image regression in the platform image itself.

**Python and dependencies.** The image pins via `uv.lock`. The CI suite plus the PostgreSQL Verification workflow gate the change; nothing about the deployment differs.

---

## 12. Troubleshooting

| Symptom | What it means | What to do |
| --- | --- | --- |
| `migrate` exits non-zero | A migration failed; the API never started | Read its log. The schema is partially applied only if the migration was non-transactional — check `alembic current` |
| API container never becomes healthy | `/health/ready` is returning 503 | `curl localhost/health/ready` — the payload names the critical component |
| `verify-deployment.sh`: *schema is at X but the image expects Y* | The API image and the database disagree | The `migrate` step did not run or did not finish. Do not "fix" this by starting the API anyway |
| `verify-deployment.sh`: *N tenant-owned table(s) have NO RLS policy* | The database was restored from a pre-SEC-002 backup, or rebuilt by hand | Stop. This is a cross-tenant exposure. Apply migrations before serving traffic |
| `verify-deployment.sh`: *outbox is growing* | The relay is alive but not keeping up, or the event bus is unreachable | Check `lacteva_outbox_pending` on the dashboard and the relay's log |
| Smoke test: *no receipt after 30s* | The payment completed but the consumer loop is not processing | **This is the failure that looks healthy.** Check `background_workers` and the consumer dashboard |
| 502 from nginx | The API is not accepting connections | Expected briefly during a deploy. Otherwise, check the API's health |
| 413 from nginx | Upload exceeded `client_max_body_size` (25m) | Raise it in `infra/nginx/nginx.conf` — this limit is invisible to the application |
| `workers_forced` in the shutdown log | A worker overran its grace period and was cancelled | Its work will be retried on the next start. Repeated occurrences mean the grace is too short for the workload |
| Login fails for every tenant user | Under RLS, an unbound session cannot see a tenant-scoped account | Confirm the token carries `tenant_id`; see [RLS-GUIDE](docs/03-architecture/05-security/RLS-GUIDE.md) §3c |

---

## 13. What this deployment does not do

Stated so it is a decision rather than a surprise:

- **No zero-downtime deploy** out of the box (§3).
- **No automated failover**, no read replica, no cross-region replication (§9).
- **No WAL archiving**, so no point-in-time recovery (§8).
- **No horizontal scaling.** One host, one database, `API_WORKERS` processes.
- **No email or SMS delivery.** NOT-001 ships logging and placeholder providers; the SMTP and SMS variables exist so the deployment is ready when an adapter lands, and so nobody believes messaging works because the settings look complete. **Suppliers are reached by SMS, and this is the gap that matters most in the field.**
- **No secret rotation automation.** Rotating means editing and redeploying.
- **PII is stored in the clear**, and there is no erasure path (ABR-002 D-2).

---

## 14. Recommended next steps

In the order that closes the largest gap first:

1. **WAL archiving and one executed PITR drill.** The documented RPO is currently fiction.
2. **An SMS adapter.** The platform generates the messages and dispatches them to a provider that discards them.
3. **Zero-downtime deploys**, which in practice means moving off single-host compose.
4. **Managed PostgreSQL** (RDS/Aurora on the `ibs` account), which delivers failover, PITR, and replicas together and removes most of §9 and §11.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by DEP-001. |
