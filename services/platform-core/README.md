# platform-core

The Lacteva **Platform Foundation** service: identity, organizations (tenants), authentication, authorization (RBAC + permission engine), configuration, audit, and the platform infrastructure ports (events, notifications, object storage, search). Business modules (e.g. Lacteva Collect) build on these — no dairy business logic lives here.

Deployment shape: a **modular monolith** whose internal modules are the future microservice seams (see `DEVELOPMENT_ROADMAP.md` at repo root for the split criteria and TODO inventory).

## Quickstart

```bash
# 1. Dependencies (uv is canonical; pip works too)
uv sync                         # or: python3 -m venv .venv && .venv/bin/pip install -e . --group dev

# 2. Infrastructure (from repo root)
docker compose up -d postgres redis rabbitmq minio

# 3. Run (dev mode auto-creates tables; real envs use Alembic)
cp .env.example .env
uv run uvicorn platform_core.main:app --reload
# → http://localhost:8000/docs (OpenAPI), /health/live, /health/ready, /metrics

# 4. Quality gates
uv run ruff check . && uv run ruff format --check .
uv run pytest                   # runs against in-memory SQLite; no infra needed
```

## Layout

```
src/platform_core/
├── core/            # shared kernel: config, logging, db, tenancy, security,
│                    # i18n, errors, observability (health/metrics/OTel hook)
├── modules/         # identity | organization | auth | authz | configuration | audit
│   └── <module>/    #   models.py (persistence) · schemas.py · service.py (use cases)
├── infrastructure/  # ports+adapters: events (RabbitMQ), notifications,
│                    # storage (MinIO/S3), search (OpenSearch)
├── api/             # deps.py (DI wiring, auth guards) · routes.py (/v1 routers)
└── main.py          # app factory + lifespan
migrations/          # Alembic (async); baseline migration is a TODO(M1)
tests/               # infra-free suite (SQLite + in-memory bus)
```

## Conventions

- **Multi-tenancy:** `Organization.id` *is* the tenant id; tenant context flows via the access token (authoritative) / `X-Tenant-ID` header (bootstrap), held in a contextvar. RLS enforcement is TODO(M1).
- **Permissions:** every key lives in `modules/authz/permissions.py`; routes guard with `Depends(require_permission("<key>"))`. Business modules extend the registry, never the engine.
- **Events:** publish `EventEnvelope.new("<domain>.<fact>.v1", {...})` via the bus port; contracts formalize later as `EVT` docs. Outbox is TODO(M1) — see `infrastructure/events.py`.
- **Errors:** raise `core.errors` types; responses are RFC 9457 problem+json, localized per `Accept-Language`.
- **Audit:** any state change calls `AuditService.record(...)` in the same transaction.

All incomplete edges carry `TODO(M#)` markers keyed to the roadmap milestones.
