---
id: DEV-ROADMAP
title: Development Roadmap — Platform Implementation
type: reference
status: Superseded
version: "1.0"
owner: Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [QR-0004, QR-0006]
baseline: ARCH-BASELINE-V1
---

# Development Roadmap — Platform Implementation

Implementation sequence for the Lacteva platform codebase. This complements the *documentation* roadmap ([QR-0004](../12-quality/QR-0004-documentation-roadmap.md)) — that one sequences documents; this one sequences code. Milestone tags (`M0`…`M4`) are referenced by every `TODO(M#)` marker in the codebase: `grep -rn "TODO(M" services/` is the live debt inventory.

## M0 — Platform Foundation ✅ (this delivery)

`services/platform-core`: modular monolith with modules **identity, organization, auth, authz (RBAC + permission engine), configuration, audit** and infrastructure ports **events (RabbitMQ), notifications, storage (MinIO/S3), search (OpenSearch)**. Multi-tenancy (org = tenant, contextvar propagation), localization (locale negotiation + catalogs), structured logging, health/readiness, Prometheus metrics, OTel hook, problem+json errors, OpenAPI, Docker + compose, Ruff, Pytest (18 tests, infra-free), pre-commit, GitHub Actions.

**Deliberate M0 simplifications** (each marked in code):

| Area | Simplification | Resolution |
| --- | --- | --- |
| Architecture record | Stack was externally dictated; no ADRs exist for it | Backfill founding ADRs (QR-0006 B4) — first doc task, not a code task |
| Event delivery | Publish-after-commit (can drop on crash) | M1: transactional outbox + relay |
| Event consumption | Not implemented | M1: consumer framework (retry, DLQ, idempotency) |
| Tenant isolation | Query-level filtering only | M1: Postgres RLS bound to session tenant |
| Refresh tokens | Stateless, irrevocable | M1: rotation + Redis jti denylist |
| Migrations | Dev/test `create_all`; no baseline committed | M1: Alembic baseline + migration-only startup outside dev |
| Permission resolution | Per-request DB query | M1: Redis cache + invalidation |
| Bootstrap | First admin assigned via test helper only | M1: `LACTEVA_BOOTSTRAP_ADMIN` one-shot startup path |
| JWT | HS256 shared secret | M1: RS256 + rotation (with auth ADR) |
| Notifications/search | Port + logging adapter / client only | M2: real channels; index projections |

## M1 — Production Hardening (before any real tenant data)

1. Alembic baseline migration; CI gate "migrations == models".
2. Transactional outbox + publisher relay; consumer framework with DLQ + idempotency keys.
3. Postgres RLS for tenant isolation; audit table append-only grants + monthly partitioning.
4. Refresh rotation, login throttling (Redis), bootstrap-admin flow, RS256 keys.
5. Readiness checks for RabbitMQ/Redis/MinIO/OpenSearch; OTel instrumentation behind the existing hook.
6. Rate limiting middleware; secrets from AWS SSM/Secrets Manager instead of env files.

## M2 — Clients & Channels

1. `apps/admin-portal` scaffold (create-next-app + shadcn) → auth, orgs, roles, config, audit slices; typed client from OpenAPI.
2. `apps/mobile` Flutter scaffold → auth + **offline-first sync engine** (the Collect prerequisite).
3. Notification channels: SES email, market SMS gateway adapter, FCM push; per-user channel preferences.
4. Search projections: audit + organization indexes fed by the event consumer.
5. Configuration: typed config schemas + market scope (ETE.LOC realization starts here).

## M3 — AWS Infrastructure (`infra/`)

1. IaC bootstrap (per infra ADR): VPC, ECS/EKS decision, RDS Postgres, ElastiCache, Amazon MQ (RabbitMQ), S3 (replaces MinIO outside local), OpenSearch Service, ECR.
2. CI extension: image push to ECR, environment promotion (staging → prod), migration job.
3. Observability stack: OTLP collector, dashboards, alerting on the metrics already exported.

## M4 — First Business Module: Lacteva Collect

Gated on: M1 complete + Collect package approval (docs pipeline B2/B3, [QR-0006](../12-quality/QR-0006-next-work-queue.md)). New module/service implementing PSP-0003…0006 (shift engine) with permissions `collect.*` added to the registry, events from PSP-0010 as first real `EVT` contracts, and the Flutter operator flows. **No Collect code before its architecture artifacts are approved** — the platform foundation deliberately contains zero dairy logic.

## Working Agreements

- Every incomplete edge is a `TODO(M#)` with an explanation — no silent gaps.
- Ruff + tests green on every commit (CI enforces); pre-commit installed locally.
- OpenAPI is the contract source for clients; regenerate typed clients, never hand-write.
- New permissions/config keys are registry entries first, code second.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Engineering | Initial roadmap with M0 delivery record and M1–M4 sequence. |
| 1.1 | 2026-08-27 | Engineering | Superseded by LACTEVA-ARCH-002 and by `LACTEVA-MASTER-PRODUCT-ROADMAP.md`, which is the live roadmap. Kept as the record of the M0–M4 sequence as it was planned on 2026-08-02. Moved to `docs/21-milestones/`; content otherwise unchanged. |
