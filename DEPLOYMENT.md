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

Twelve containers, one published port.

| Service | Purpose | Reachable from outside? |
| --- | --- | --- |
| `nginx` | TLS termination, compression, rate limiting, the only front door | **Yes** — 80/443 |
| `portal` | The admin portal (Next.js). Holds the browser session and proxies to `api` | No |
| `api` | The platform. Uvicorn, N workers | No |
| `rabbitmq` | Event transport | No |
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
- **`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, `LACTEVA_APP_PASSWORD`** — generate them: `openssl rand -base64 36`.
- **`LACTEVA_APP_USER`** — the role the API connects as. It **must differ from `POSTGRES_USER`**; see §2b, which is the single most consequential setting on this page.
- **`LACTEVA_CORS_ORIGINS`** — a JSON list of exact origins. Never a wildcard.

### TLS certificates (TLS-001)

`lacteva.conf` has always served `/.well-known/acme-challenge/` from
`/var/www/certbot`, and nothing mounted a volume there — so the documented
certbot step could not have worked. The `certbot_webroot` volume is now shared
between nginx and certbot, and issuance is:

```bash
# DNS must already point at this host — every name, or the challenge for the
# one that does not resolve fails and takes the whole issuance with it.
docker run --rm \
  -v /etc/lacteva/letsencrypt:/etc/letsencrypt \
  -v lacteva-production_certbot_webroot:/var/www/certbot \
  certbot/certbot:latest certonly --webroot -w /var/www/certbot \
  -d your.domain --agree-tos --non-interactive --cert-name lacteva \
  --email ops@your-domain            # or --register-unsafely-without-email

sudo cp -L /etc/lacteva/letsencrypt/live/lacteva/fullchain.pem /etc/lacteva/certs/
sudo cp -L /etc/lacteva/letsencrypt/live/lacteva/privkey.pem   /etc/lacteva/certs/
sudo chmod 600 /etc/lacteva/certs/privkey.pem
```

nginx reads from `TLS_CERT_DIR`, not from certbot's live directory, so a
renewal must copy the files across and reload. `infra/deploy/renew-tls.sh`
does both and is driven by the `lacteva-tls-renew.timer` unit twice a day —
certbot only acts inside the last 30 days, so it usually does nothing.
`--dry-run` exercises the whole path without issuing.

**The deployed certificate carries four names**: `lacteva.com`,
`www.lacteva.com`, `app.lacteva.com` and `api.lacteva.com`. Adding or removing
one is the full `-d` list again with the same `--cert-name lacteva`, so the
renewal timer keeps working on the same lineage:

```bash
... certonly --webroot -w /var/www/certbot --cert-name lacteva \
  -d lacteva.com -d www.lacteva.com -d app.lacteva.com -d api.lacteva.com
```

Use `--expand` when the list GROWS. When it shrinks, certbot needs the shorter
list plus the same `--cert-name`; it replaces the lineage rather than
extending it, and `renew-tls.sh` picks up whatever that lineage now holds.

`dev.phoenixsoft.in` was on this list until 2026-09-03 and is not any more
(owner's decision). Removing a name is not just a certificate change: the
server block that claimed it and the CORS origin that trusted it go at the
same time, or the name half-exists — served under a certificate that no longer
covers it, which every browser reports as a security failure rather than as a
site that moved.

`LACTEVA_CORS_ORIGINS` is NOT how the portal reaches the API — it calls
through its own same-origin proxy — so this list names only clients that make
genuine cross-origin browser calls, and stays short by default.

Put `fullchain.pem` and `privkey.pem` in `TLS_CERT_DIR`. To terminate TLS at a load balancer instead, point traffic at port 80 and remove the redirect block from `infra/nginx/conf.d/lacteva.conf`.

**Sanity check before you start anything:**

```bash
docker compose -f docker-compose.production.yml --env-file .env.production config >/dev/null
```

That resolves every variable and fails loudly on a missing one — cheaper than discovering it half-started.

---

## 2b. Database roles — why the API is not the superuser

Set two roles, and do not collapse them into one:

| Variable | Role | Used by |
| --- | --- | --- |
| `POSTGRES_USER` | owns the schema, **superuser** | Alembic, `pg_dump`, `pg_restore` |
| `LACTEVA_APP_USER` | `NOSUPERUSER NOBYPASSRLS`, no DDL | the API and the background workers |

**A PostgreSQL superuser ignores row-level security completely.** This is not
softened by `FORCE ROW LEVEL SECURITY` — `FORCE` closes the loophole for the
table *owner* and says nothing at all about superusers.

Until VER-001 the API connected as `POSTGRES_USER`, which the official
`postgres` image creates as a superuser. Every policy built by SEC-001,
SEC-002 and MT-001 was therefore **inert in production**: enabled, forced,
listed in `pg_policies`, and enforcing nothing. Tenant isolation was
application-level only — exactly the dependency row-level security exists to
remove. Nothing would have alerted, because the deployment check verified that
policies *existed*, and they did.

Two things now make that failure loud rather than silent:

- `infra/postgres/init/10-application-role.sh` creates the application role on
  first start, with `NOSUPERUSER NOBYPASSRLS` set explicitly.
- The platform **refuses to start** in `prod` and `staging` if it finds itself
  connected as a role that bypasses RLS (`assert_rls_is_enforceable`), and
  `verify-deployment.sh` asserts the same thing from outside.

### An existing database

The init script runs only on an **empty** data directory, so an upgrade will
not pick it up. Apply it by hand, once, as the owner:

```sql
CREATE ROLE lacteva_app LOGIN PASSWORD '<generate one>';
ALTER ROLE lacteva_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE lacteva TO lacteva_app;
GRANT USAGE ON SCHEMA public TO lacteva_app;
REVOKE CREATE ON SCHEMA public FROM lacteva_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lacteva_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lacteva_app;
-- so a table added by a future migration needs no further grant:
ALTER DEFAULT PRIVILEGES FOR ROLE lacteva_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lacteva_app;
ALTER DEFAULT PRIVILEGES FOR ROLE lacteva_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO lacteva_app;
```

Then set `LACTEVA_APP_USER` / `LACTEVA_APP_PASSWORD` and redeploy. Verify:

```sql
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'lacteva_app';
-- both flags must be false
```

If the platform starts, this held. That is the point of asserting it at
startup rather than documenting it here.

---

## 3. Deploying

### Where the images are built (DEMO-010)

**Not on the machine that serves the platform.** `.github/workflows/images.yml`
builds both images on a GitHub runner and pushes them to ECR; the host only
ever pulls.

That is not a preference. Building on the host failed with `spawn ENOMEM`
during DEMO-009 — the host runs `vm.overcommit_memory=2`, so forking a Next.js
build worker requires commit charge equal to the parent's reservation and is
refused while the platform is also resident. The same week, build cache took
the disk to 100% twice. A 2 vCPU / 4 GB instance was doing a compiler's job and
a server's job at once.

    git → GitHub Actions → docker build → ECR → the EC2 pulls

No AWS key is stored in GitHub: the runner exchanges its OIDC token for a
session on `lacteva-github-actions-ecr`, whose trust policy admits only this
repository's branches and tags — never a pull request, which must not be able
to publish an image — and whose permissions reach only the two Lacteva ECR
repositories. Nothing about this recurs in cost: GitHub's runners, an ECR
repository that already existed, free intra-region pulls, and IAM.

A push to `main` that touches either tree publishes `main-<short sha>`. To
publish a named release tag, run the workflow manually with a `tag` input.
**Both images must exist at the same tag before deploying** — the workflow's
final job says so explicitly, because a tag where only one of them exists is a
half-deployable release.

Building on the host is still possible and is the documented emergency path
(the portal Dockerfile's `NODE_HEAP_MB` default stays small precisely so that
it works there), but it is no longer how releases are made.

### On the host

```bash
# The tag was published by CI; the host pulls it.
sudo /opt/lacteva/current/infra/deploy/deploy.sh main-<short sha>
```

`deploy.sh` pulls, migrates, deploys, verifies, smoke-tests, and rolls back
automatically if any of that fails. The equivalent by hand:

```bash
sed -i "s/^LACTEVA_IMAGE_TAG=.*/LACTEVA_IMAGE_TAG=$TAG/" .env.production

docker compose -f docker-compose.production.yml --env-file .env.production up -d

./infra/deploy/verify-deployment.sh
./infra/deploy/smoke-test.py --base-url https://api.example.com
```

**What happens in `up -d`, in order.** Nothing waits on a timer:

1. `postgres` and `redis` start. Compose waits for their health checks — `pg_isready` and a `PING` that must answer `PONG`.
2. `migrate` runs `alembic upgrade head` and exits. **A failure here stops the deployment**: `restart: "no"` means it does not retry, so the API's `service_completed_successfully` condition never fires and nothing serves traffic against a schema that did not apply.
3. `api` starts, and is *healthy* only once `/health/ready` returns 200 — which now means every probe is non-critical, not merely that the database answered (§6).
4. `portal` starts once the API is healthy, and is *healthy* once its own `/api/health` answers. That check is deliberately about the portal only — a database maintenance window must not restart a working frontend.
5. `nginx` starts once BOTH the API and the portal are healthy, and publishes the port.

A sleep anywhere in that chain would be a guess: too short and it fails under load, too long and it taxes every deploy forever. `tests/test_deployment.py::test_nothing_in_production_waits_on_a_sleep` keeps it that way.

### The admin portal (PORTAL-001)

The portal is a **server**, not a static bundle: it holds the browser's session
in an HttpOnly cookie and proxies every API call itself. That is what keeps a
session token out of reach of page script, and it is why there is a `portal`
container rather than a directory of files behind nginx.

**One image, any environment.** The portal reads `LACTEVA_API_URL` from its
environment at request time. There is deliberately no `NEXT_PUBLIC_API_URL`
build argument: Next inlines `NEXT_PUBLIC_*` into the browser bundle at build
time, so an image built with one would only ever reach one backend, and an
image built without it shipped `http://localhost:8000` to production browsers.
Nothing secret is baked into the image, and no build argument is required.

```bash
# CI does this; on the host it is the emergency path only. NODE_HEAP_MB
# defaults to 768 so that the constrained host can still complete a build;
# the workflow passes 4096 because a runner has the room.
docker build -t lacteva/admin-portal:$TAG apps/admin-portal
```

**Routing.** One TLS boundary, two upstreams:

| Path | Goes to | Why |
| --- | --- | --- |
| `/` and everything unmatched | `portal` | The product a person opens |
| `/_next/static/` | `portal` | Content-hashed, cached immutably |
| `/v1/` | `api` | The mobile client and integrations |
| `/health/live`, `/health/ready` | `api` | Platform health |
| `/metrics` | `api` | Internal networks only |
| `/docs`, `/redoc`, `/openapi.json` | `api` | Exact matches, so they cannot shadow a portal route |

The browser never learns the platform's address: it talks only to the portal's
own origin, and the portal talks to `http://api:8000` on the compose network.
The API therefore needs no public hostname and no CORS entry for the portal.

**Sessions.** `POST /api/auth/login` exchanges credentials for cookies
(`HttpOnly`, `SameSite=Strict`, `Secure` in production) and returns no body.
`POST /api/auth/logout` revokes the platform session as well as clearing the
cookies — clearing the cookie alone would leave a captured refresh token
working. CSRF is covered by `SameSite=Strict` plus an `Origin` check on every
state-changing route; the backend still never sees a cookie, so its
bearer-only, CSRF-free posture (divergence #22) is unchanged.

**If the portal cannot reach the API**, it answers `502` rather than `500`.
That distinction is what tells an operator reading nginx logs whether the
frontend or the backend is the problem.

### Mobile release builds (PORTAL-001 / F-05)

Release builds were signed with the **public Android debug key** — not
distributable, not upgradeable. They now fail unless a real keystore is
supplied.

```bash
cp apps/mobile/android/key.properties.example apps/mobile/android/key.properties
# point storeFile at the keystore, fill in the passwords, then:
cd apps/mobile && flutter build apk --release \
  --dart-define=LACTEVA_API_URL=https://lacteva.example
```

`android/key.properties` and every `*.jks` / `*.keystore` are gitignored and
must never be committed. In CI, write `key.properties` from secrets
immediately before the build and delete it immediately after; do not export
the passwords as environment variables a build log could echo.

**The keystore is a permanent credential.** Lose it and the app can never be
upgraded again — a new key means a new listing and every user reinstalling.
Back it up where more than one person can reach it, and treat it like the JWT
signing key.

Note the `--dart-define`: without it a release build defaults to
`http://localhost:8000`. The same flag also compiles the mock scale and
analyzer controls out of the build (SEC-003/F-01), which `kReleaseMode`
already does by default.

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

**Scale limit, stated plainly:** the logical backup reads every row into JSONL. At the volumes DBD-0001 models, this is a portability and verification mechanism, not a four-hour recovery mechanism.

Physical `pg_basebackup` + WAL **is now executed and proven** (PITR-001) — recovery to a timestamp, a transaction boundary, a named restore point, and latest, each asserting that work after the target is absent. See [PITR](docs/03-architecture/06-operations/PITR.md) and run `./infra/ci/pitr-proof.sh`.

---

## 9. Disaster recovery

[DISASTER_RECOVERY](docs/03-architecture/06-operations/DISASTER_RECOVERY.md) names the disasters and their RPO/RTO. Two things a deployer must know:

- **There is no automated failover.** Recovery is a deliberate human decision, by design at this stage. At scale it is a multi-hour outage and should be replaced with managed failover (RDS Multi-AZ / Aurora) rather than something built here.
- **The 5-minute RPO is now achievable.** `archive_mode=on`, an `archive_command` that refuses to overwrite, and `archive_timeout=60` are configured in `docker-compose.production.yml`, and a point-in-time restore has been performed against a real cluster. The bound is `archive_timeout`, not the age of a backup.

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
- **The WAL archive is a local Docker volume.** PITR works; surviving total host loss needs the archive replicated off-host (§8).
- **No horizontal scaling.** One host, one database, `API_WORKERS` processes.
- **No email delivery.** NOT-001 ships logging and placeholder providers for email; the SMTP variables exist so the deployment is ready when an adapter lands, and so nobody believes email works because the settings look complete.
- **SMS delivery IS wired (MSG-001)** and must be configured deliberately: set `LACTEVA_NOTIFICATION_SMS_PROVIDER`, and run staging in `dry_run` first — a wrong sender id is a permanent rejection, and discovering that in production means suppliers silently stop being told they were paid.
- **No secret rotation automation.** Rotating means editing and redeploying.
- **PII is stored in the clear**, and there is no erasure path (ABR-002 D-2).

---

## 14. Recommended next steps

In the order that closes the largest gap first:

1. **Replicate the WAL archive off-host** and monitor `pg_stat_archiver.failed_count`. PITR itself is proven; a local archive is not a disaster-recovery archive.
2. **An SMS adapter.** The platform generates the messages and dispatches them to a provider that discards them.
3. **Zero-downtime deploys**, which in practice means moving off single-host compose.
4. **Managed PostgreSQL** (RDS/Aurora on the `ibs` account), which delivers failover, PITR, and replicas together and removes most of §9 and §11.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-06 | Architecture Board | Established by DEP-001. |


## Production configuration that now FAILS CLOSED (PROD-001)

The process refuses to start in `prod` on any of these. Each was a way for a
deployment to look healthy while doing nothing, or to run on a credential that
was never meant to leave a laptop.

| Setting | Refused value | Why |
| --- | --- | --- |
| `LACTEVA_DATABASE_URL` | non-PostgreSQL, or `lacteva:lacteva@` / `postgres:postgres@` | RLS, exact aggregation and the backup format all require PostgreSQL; the dev credential is in this repo's own compose files |
| `LACTEVA_RLS_ENABLED` | `false` | It is the tenant boundary — and disabling it also disables the check that detects a role which bypasses RLS |
| `LACTEVA_NOTIFICATION_SMS_PROVIDER` | `logging`, `placeholder` | Both return ACCEPTED and send nothing |
| `LACTEVA_NOTIFICATION_EMAIL_PROVIDER` | `logging`, `placeholder` | As above. Use `smtp`, or `disabled` to fail visibly |
| `LACTEVA_EVENT_BUS` | `memory`, `null` | Accept every publish and deliver nothing |
| `LACTEVA_OUTBOX_MODE` | `inline` | Dispatches inside the request transaction; bypasses retry and the DLQ |
| `LACTEVA_RATE_LIMIT_BACKEND` | `memory` | Per-process, so each replica grants the full budget again |
| `LACTEVA_RECEIPT_PDF_RENDERER` | `placeholder` | Cannot produce a printable receipt |
| `LACTEVA_BACKUP_OFFSITE_ENDPOINT` | unset | Backups would live only on the database's own volume, which is not a backup (BKP-003) |
| `LACTEVA_BACKUP_OFFSITE_SECURE` | `false` | A backup in flight carries every farmer's records |
| `LACTEVA_BACKUP_OFFSITE_RETAIN` | `< 1` | "Keep zero backups" is never an instruction anyone means |
| `LACTEVA_NOTIFICATION_SMS_PROVIDER=http` | with no `SMS_API_URL`/`SMS_API_KEY` | Fails per message instead of failing the deploy once |
| `LACTEVA_NOTIFICATION_EMAIL_PROVIDER=smtp` | with no `SMTP_HOST` | As above |

`dry_run` and `disabled` remain legal on both channels: both are deliberate.
Email has no transport beyond SMTP, so a deployment without a mail relay must
say `disabled` rather than pretend.

### Database roles

Full rationale in [DBD-0002 §4](docs/07-data/DBD-0002-integrity-lifecycle-and-numbering.md).

```sql
-- Migrations run as the owner; the application never performs DDL.
CREATE ROLE lacteva_app LOGIN PASSWORD '<from a secret>';
ALTER ROLE lacteva_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE lacteva TO lacteva_app;
GRANT USAGE ON SCHEMA public TO lacteva_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO lacteva_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO lacteva_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO lacteva_app;
```

**A superuser ignores every RLS policy, including `FORCE`.** The application
refuses to start in `prod`/`staging` when its role is `SUPERUSER` or has
`BYPASSRLS` — this is the defect VER-001 found, where every policy was visible
in `pg_policies` and enforcing nothing.

**PgBouncer must run in `transaction` mode.** RLS binds the tenant with
`SET LOCAL`, which is transaction-scoped; in `statement` mode a pooled
connection can serve a query under another request's tenant.

### Tenant offboarding

`GET /v1/tenant-data/export` → `GET /v1/tenant-data/offboarding-plan` →
`POST /v1/tenant-data/offboard` (confirmation = the organization's exact name).
Operational data is purged, financial and audit records are anonymized and
retained, the organization becomes a tombstone. Irreversible — take the export
first.


## Off-site backups (BKP-003)

The nightly job now takes the backup, verifies it, **replicates it off-site**,
and only then prunes — in that order, because the worst case must be too many
copies rather than none.

```bash
LACTEVA_BACKUP_OFFSITE_ENDPOINT=s3.eu-central-1.amazonaws.com
LACTEVA_BACKUP_OFFSITE_ACCESS_KEY=...      # from a Docker secret, never inline
LACTEVA_BACKUP_OFFSITE_SECRET_KEY=...
LACTEVA_BACKUP_OFFSITE_BUCKET=lacteva-backups
LACTEVA_BACKUP_OFFSITE_SECURE=true
LACTEVA_BACKUP_OFFSITE_RETAIN=30
```

**The endpoint must be in a different failure domain from the database host.**
Pointing it at the MinIO in `docker-compose.production.yml` satisfies the
configuration check and defeats the entire purpose — that container dies with
the volume. Use the cloud provider's object storage, or a bucket somewhere the
database host cannot take with it.

**Enable bucket encryption at rest** (SSE-S3 or SSE-KMS). The platform does not
encrypt the archive itself: client-side encryption puts a key in the recovery
path, and a backup you cannot decrypt during an incident is not a backup.

### Recovering when the host is gone

```bash
python -m platform_core.core.backup.cli offsite-list
python -m platform_core.core.backup.cli offsite-fetch <backup-id> /restore/here
alembic upgrade head                      # fresh database, schema first
python -m platform_core.core.backup.cli restore /restore/here
python -m platform_core.core.backup.cli integrity
```

`offsite-fetch` re-computes the archive checksum from the downloaded bytes and
refuses a mismatch, so a corrupt object cannot be restored. This exact sequence
is executed by `./infra/ci/offsite-proof.sh` with the local backup directory
deleted first.


## What DEPLOY-001 executed, and what it could not (2026-08-09)

The container stack was **not** started. This machine has no root and Ubuntu
24.04's `apparmor_restrict_unprivileged_userns=1` denies unprivileged user
namespaces, so no container runtime — Docker, Podman, containerd — can run at
all. That is a hard environmental boundary, not a missing package, and lifting
it requires root.

What WAS executed, against the real files, with the real tools:

| Step | Tool | Result |
| --- | --- | --- |
| Terraform (hetzner, aws) | `terraform 1.9.8` init / validate / fmt | **PROVEN** — after fixing two defects that made both configs invalid |
| SSH exposure guard | `terraform plan` | **PROVEN** — `0.0.0.0/0` refused at plan time |
| Terraform plan/apply | — | **BLOCKED** — stops at provider authentication; needs a real cloud account |
| Compose stack | `docker compose 2.29.7 config` | **PROVEN** — 10 services resolve; only nginx publishes ports |
| Production configuration | the platform's own validator, fed the resolved container environment | **PROVEN** — after fixing four defects that stopped it starting |
| nginx | `nginx 1.27.3 -t` (the pinned version) | **PROVEN** — `syntax is ok` |
| cloud-init | `cloud-init 26.1` schema, on the Terraform-rendered output | **PROVEN** — valid |
| systemd units | `systemd-analyze verify` | **PROVEN** — well-formed |
| Deployment scripts | `bash -n` | **PROVEN** — 11/11 parse |
| Container runtime, TLS issuance, failure/restart tests, rollback | — | **BLOCKED BY ENVIRONMENT** |

**TLS is NOT proven.** The nginx TLS block parses and loads a certificate, but
no certificate was issued and no handshake was performed. Treat the first real
`certbot` run as an unexecuted step.

**Rollback is NOT proven.** `LACTEVA_IMAGE_TAG` makes the application rollback
a one-variable change and the compose file is structured for it, but no
deployment was rolled back. The database boundary is unchanged and unchanged
deliberately: expand-only migrations roll back freely, contract migrations do
not, and `alembic downgrade` on a live database drops columns holding data
written since the upgrade. Roll forward or restore.
