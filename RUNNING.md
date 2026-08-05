---
id: RUNNING
title: Running the Lacteva Platform Locally
type: reference
status: Approved
version: "1.1"
owner: Engineering
created: 2026-08-02
last-updated: 2026-08-06
baseline: ARCH-BASELINE-V1
---

# Running Lacteva Locally

From clone to a running platform on a new machine.

## Prerequisites

| Tool | Needed For | Version |
| --- | --- | --- |
| Docker + Compose | Infrastructure, backend, portal containers | recent |
| GNU Make | The entry-point commands | any |
| uv (or Python 3.12+) | Backend outside Docker, tests | latest |
| Node.js + npm | Portal outside Docker | 22+ |
| Flutter SDK | Mobile app (optional for backend work) | 3.38+ stable |

## The One Command

```bash
git clone git@github.com:valorantstech/lacteva.git && cd lacteva
make dev
```

`make dev` builds and starts PostgreSQL, Redis, RabbitMQ, MinIO, the backend (`platform-core`), and the admin portal. First start takes a few minutes (image builds + npm install).

| What | URL | Notes |
| --- | --- | --- |
| Backend API | http://localhost:8000 | OpenAPI UI at `/docs`, schema at `/openapi.json` |
| Health | http://localhost:8000/health/ready | `{"status":"ok","checks":{"database":true}}` |
| Metrics | http://localhost:8000/metrics | Prometheus format |
| Admin portal | http://localhost:3000 | Live platform status dashboard |
| RabbitMQ UI | http://localhost:15672 | `lacteva` / `lacteva` |
| MinIO console | http://localhost:9001 | `lacteva` / `lacteva-secret` |
| OpenSearch (optional) | http://localhost:9200 | `docker compose --profile search up -d` |

**Verify:** `curl -s localhost:8000/health/ready` returns status `ok`; the portal at `:3000` shows a green *database → healthy* row.

## The Mobile App

Flutter needs a device or emulator, so it runs on the host:

```bash
make mobile                      # Android emulator (API at http://10.0.2.2:8000)
make mobile DEVICE=chrome LACTEVA_API_URL=http://localhost:8000   # browser
flutter devices                  # list device ids
```

`10.0.2.2` is how the Android emulator reaches your host machine.

## Database Migrations

```bash
make infra      # postgres up
make migrate    # alembic upgrade head (baseline schema 6a09fed0151a)
make migration m="describe your change"   # autogenerate a new migration
```

In `LACTEVA_ENV=dev|test` the backend also auto-creates tables at startup for convenience; staging/prod run migrations only.

## Proving It On PostgreSQL

`make dev` runs the platform. It does not prove the guarantees that only a real engine can exercise — row-level security, migrations from an empty database, and a restore into a fresh one. That is a separate, throwaway run:

```bash
docker compose -f docker-compose.proof.yml run --rm proof
```

Nine steps, any failure fails the run, and it is the **identical script** CI executes. The database has no volume and no published port: every run starts empty, because "migrations apply from empty" is one of the things being proven. Nothing touches your dev database.

Details, per-step meaning, and how to read a failure: [POSTGRES-PROOF](docs/03-architecture/06-operations/POSTGRES-PROOF.md).

## Everyday Commands

```bash
make help        # all targets
make backend     # backend on the host with --reload (fastest loop)
make portal      # portal on the host with reload
make test        # backend + mobile test suites
make lint        # ruff
make stop        # stop everything          make clean  # ...and delete volumes
```

## Troubleshooting

- **Port already in use** — something on 5432/6379/5672/8000/3000; `make stop` first, or stop the local service occupying the port.
- **Portal container slow on first start** — it runs `npm install` into a named volume once; subsequent starts are fast. Alternative: `make portal` on the host.
- **No Docker available** — backend works without any infrastructure for tests (`make test-backend` uses SQLite in memory); for a live server without Docker, set `LACTEVA_DATABASE_URL=sqlite+aiosqlite:///./dev.db` in `services/platform-core/.env` and run `make backend`'s uvicorn line manually without the postgres URL.
- **Emulator can't reach backend** — use `10.0.2.2`, not `localhost` (see above).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-06 | Engineering | PostgreSQL proof section (CI-001). |
| 1.0 | 2026-08-02 | Engineering | Initial version (SPRINT-001). |
