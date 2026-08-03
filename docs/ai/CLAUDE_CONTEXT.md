---
id: CLAUDE-CONTEXT
title: Lacteva AI Engineering Context — Permanent Onboarding Guide
type: reference
status: Approved
version: "1.3"
owner: Engineering
created: 2026-08-03
last-updated: 2026-08-03
related: [CAP-0001, PDT-0001, QR-0006]
baseline: ARCH-BASELINE-V1
---

# Lacteva AI Engineering Context

**Read this document first.** It is the permanent onboarding guide for every engineer — human or AI — who joins Lacteva. It explains what the platform is, what exists, what is locked, and how work is done here. It consolidates; it does not override: on any conflict, [ARCHITECTURE_BASELINE_V1](../../ARCHITECTURE_BASELINE_V1.md) and the documents it locks win.

**Reading order after this file:** [ARCHITECTURE_BASELINE_V1](../../ARCHITECTURE_BASELINE_V1.md) → [CHANGELOG](../../CHANGELOG.md) (the platform's evolution, newest first) → [DEVELOPMENT_ROADMAP](../../DEVELOPMENT_ROADMAP.md) → the module you are about to touch, *tests first*.

---

## 1. Vision

**Lacteva is an AI-first, cloud-native, multi-tenant Dairy Intelligence Platform.** The long-term mission is to digitize the entire dairy value chain — from the farmer pouring milk at a village collection center to processing, settlement, and market intelligence — for **1,000,000+ dairy businesses across 50+ countries**.

**Why it exists.** Dairy in most of the world runs on paper registers, disconnected spreadsheets, trust-based measurement, and month-end settlement disputes. Milk is perishable, quality-priced, and collected twice daily from thousands of small suppliers — a domain where digitization compounds: accurate weights and quality readings feed fair pricing, fair pricing feeds farmer trust and retention, and the resulting data feeds credit, breeding, nutrition, and market decisions no participant can make today.

**Customers.** Dairy cooperatives and their unions, private chilling-center networks, mid-size dairies and processors, and (later) enterprise mega-dairies. The paying customer is the *organization*; the daily users are collection-center operators, field staff, quality labs, accountants, and managers. Farmers/suppliers are first-class subjects of the system before they are users of it.

**Problems solved (in build order).** Trustworthy milk collection (identity, weight, quality, immutable transaction records) → transparent quality-based pricing → supplier settlement → operations intelligence → the wider capability universe documented in the [Business Capability Model](../05-capabilities/CAP-0001-business-capability-master-map.md): **10 domains, ~40 subdomains, 86 capabilities** — the authoritative map of everything Lacteva may ever build.

**Short-term goal.** A production-grade procurement core: collection centers, suppliers, operational readiness, the milk collection transaction engine, and the Pricing Platform — on a platform foundation (identity, tenancy, RBAC, events, audit) that was deliberately built *before* any dairy logic.

## 2. Product Philosophy

- **Business capabilities over CRUD.** Features trace to capabilities (CAP IDs), not to database tables. A screen exists because a capability needs it.
- **Platform before product.** Identity, organizations, permissions, configuration, audit, and events were built first, with zero dairy logic. Every business module composes them; none reimplements them.
- **Configuration before customization.** Variability is data, not forks: quality dimensions are rows, not code; configuration resolves global → tenant; markets get parameters, not branches.
- **Offline-first (destination).** Collection happens where connectivity fails. The Flutter app currently calls the API directly; the offline sync engine is scheduled platform work (M2) and *the* prerequisite for full Collect field deployment.
- **Mobile-first.** The operator at 5 a.m. with a queue of farmers is the primary persona. The portal administers; the mobile app operates.
- **AI-ready.** Every capability documents its AI opportunities (CAP catalogs); the event stream and immutable transaction records are the future training substrate; `AGT` (AI agent) is a reserved architecture artifact type. No ML is deployed yet — the data discipline that enables it is.
- **Global-ready.** 50+ countries: i18n (en/sw/hi so far), IANA timezones per center, ISO-4217 currency on every rate card, and **no country-specific rules hardcoded anywhere**.
- **Event-driven.** Every business fact is published as a versioned event through the Relay. Future modules subscribe; they do not poll or reach into other modules' tables.

## 3. Engineering Philosophy

- **DDD, pragmatically.** Bounded contexts are the module folders under `platform_core/modules/`. Aggregates own invariants (e.g., a rate card owns its scope and matrices); cross-module access goes through application services and events, never through another module's tables. SQLAlchemy models double as entities — a documented pragmatism, not an accident.
- **Clean Architecture, pragmatically.** Direction of dependency: API routes → application services → models/infrastructure ports. Routers never touch the session or construct services; DI lives in `api/deps.py` (the composition root). Infrastructure is behind ports (`EventBus`, `ObjectStorage`, `Notifier`, hardware adapters) with real and in-memory/mock implementations.
- **Modular monolith.** One deployable (`services/platform-core`), many modules. Modules are the future service seams; the split criteria live in the roadmap. Do not extract services prematurely; do not couple modules so they cannot be extracted.
- **Relay / transactional outbox (SPRINT-008A).** The DI-injected `Bus` is `OutboxEventBus`: publishing writes an `event_outbox` row *inside the caller's transaction*. Rollback discards the event with the business change; commit guarantees delivery (dispatcher → CAS claim → retry with exponential backoff → dead-letter queue → replay). The event id is the message id is the idempotency key. **Never bypass it** — `get_event_bus()` is the transport, not the API.
- **Test-first mindset.** Behavior is specified by API-level tests against an in-memory stack (SQLite + in-memory bus + inline outbox — no infrastructure needed). Every work order sets a minimum test count; every bug fix lands with a regression test; the suite is green on every commit.
- **Business rules are register-defined.** The [Business Rules Register](../03-architecture/01-business-layer/BUSINESS-RULES.md) (`BR-NNNN` IDs) is the source of truth for platform invariants — BR-0001 published-card immutability, BR-0002 single active card per scope, BR-0003 exactly-one resolution, BR-0004 non-overlapping bands, and growing. New rules get a register entry, enforcing code citing the ID, and verifying tests in the same change; register↔code divergence is a defect.
- **Business objects & canonical data model.** One canonical model per concept, owned by one module (Supplier by `supplier`, RateCard by `pricing`, …). Other modules reference by id and consume events. Immutability is a first-class state: completed milk transactions, published rate cards, and active matrices are never edited — corrections are new versions or (future) adjustment transactions.
- **Concurrency by CAS.** State transitions that must not race use `UPDATE … WHERE status = <expected>` with a rowcount check (transaction accept/reject, rate card publish, outbox claim). Prefer this over `SELECT FOR UPDATE` — it is portable to the SQLite test stack.

## 4. Current Architecture

**Shape.** FastAPI modular monolith (`platform-core`) + PostgreSQL (SQLite in tests/dev-lite) + Redis + RabbitMQ + MinIO + OpenSearch, with a Next.js admin portal and a Flutter mobile app. All API under `/v1`, OpenAPI-documented, problem+json errors, Prometheus metrics, structured logging with request/correlation ids.

**Tenancy.** `Organization.id` **is** the tenant id. Tenant-scoped tokens are authoritative; platform principals act inside a tenant via `X-Tenant-ID` (permission-guarded). A contextvar carries tenant context; every query filters by it (Postgres RLS is planned hardening, M1).

**Identity & access.** Server-side sessions with hashed, rotating refresh tokens and reuse-as-theft revocation; access JWTs bound to a session id and revoked with it. RBAC: central permission registry (`modules/authz/permissions.py`, keys `<module>.<entity>.<action>`), `require_permission()` route guards, system roles (`platform-admin` = wildcard, `tenant-admin`, `tenant-viewer`) synced at startup.

**Bounded contexts (modules) — all completed and tested:**

| Module | Owns |
| --- | --- |
| `identity` | Users, credentials, registration |
| `auth` | Login, sessions, refresh rotation, logout, password-reset foundation |
| `authz` | Roles, permission registry, permission engine |
| `organization` | Organizations (= tenants), workspaces, branches, membership, invitations |
| `configuration` | Key-value configuration with global→tenant resolution |
| `audit` | Append-oriented audit trail of every mutation |
| `collection_center` | Centers under branches, status lifecycle, config, operating hours, business calendar |
| `operational_readiness` | Device registry (6 categories), assignment, health, operator assignment, readiness engine (READY/WARNING/NOT_READY) |
| `supplier` | Suppliers, profiles, documents, bank accounts, m:n center placement, HMAC-signed QR identity, search, bulk import |
| `milk_collection` | Collection sessions (readiness-gated) + the immutable milk transaction engine (state machine NEW→…→COMPLETED, snapshot, ordered event log, metrics; pricing placeholder `awaiting_pricing_engine`) |
| `event_relay` | Transactional outbox, dispatcher, retry, DLQ, replay, `/_relay` operations API |
| `pricing` | Rate cards (workflow draft→under_review→approved→published→archived, versioning, center+product scope, effective-date overlap rule), pricing matrices (configurable quality dimensions, half-open price bands), the read-side Resolution Engine (PRC-003: exactly-one band selection with structured no-match/integrity exceptions), and the Pricing Calculator (PRC-004: Decimal-only gross = price × quantity with configurable rounding, full trace, `pricing.calculated.v1`) |

**Products.** *Platform products:* platform-core API, admin portal, mobile app. *Business products:* **Lacteva Collect** (specified in PSP-0001…0010; partially realized by the milk-collection engine) and the **Pricing Platform / Rate Management** (Increments 001–002 delivered). The documented product object is [PDT-0001](../03-architecture/03-application-layer/PDT-0001-lacteva-collect.md).

**Business objects in production:** Organization, Workspace, Branch, User, Role, CollectionCenter (+config/hours/calendar), Device, OperatorAssignment, Supplier (+profile/documents/bank accounts/placements), CollectionSession, MilkCollectionTransaction (+events/snapshot/metrics), OutboxEvent/EventDelivery/DeadLetter, RateCard (+center/product assignments), QualityDimension, PricingMatrix (+rows).

**Event infrastructure.** `EventEnvelope` (id, type, source, time, tenant, actor, trace/correlation/causation ids, aggregate type+id, version, payload); wire names `<domain>.<past-tense-fact>.v<major>` (e.g. `collection.transaction-accepted.v1`, `pricing.rate-card-published.v1`); RabbitMQ topic exchange `lacteva.events` (routing key = event type); everything durable through the outbox. **Not yet built:** the consumer framework (subscriptions, handler idempotency, consumer DLQ) — the recommended "Relay part 2".

## 5. Repository Structure

| Path | Purpose |
| --- | --- |
| `services/platform-core/` | The backend monolith. `src/platform_core/{api,core,infrastructure,modules}`, `migrations/` (Alembic, async), `tests/` (one file per module area, shared fixtures in `conftest.py`). |
| `apps/admin-portal/` | Next.js 16 + TypeScript + Tailwind + shadcn/ui (on Base UI — **no `asChild`**). Hand-typed API client in `src/lib/api.ts`; one page folder per business area. Administration & back-office. |
| `apps/mobile/` | Flutter operator app. `lib/src/api.dart` (single `ApiClient`, methods overridable for widget-test fakes), one file per feature area, widget tests in `test/widget_test.dart`. Field operations. |
| `docs/` | The governed documentation workspace: `00-standards` (STD), `01-governance` (GOV), `02-templates` (TPL), `03-architecture` (five-layer EA workspace + `adr/`), `05-capabilities` (CAP — the 86-capability model), `09-events`, `11-glossary`, `12-quality` (QR audits/roadmaps), `13-products` (PSP Collect package), plus `INDEX`, `NAVIGATION`, generated `XREF`. |
| `docs/ai/` | AI-engineer context (this document). |
| `tools/` | `validate/validate_docs.py` (front-matter/ID/link/version validator) and `xref/generate_xref.py` (cross-reference map). Both are CI gates. |
| `infra/` | Reserved for AWS IaC (M3). Currently a placeholder — do not add cloud dependencies ahead of it. |
| `libs/` | Reserved for shared libraries when a second service exists. |
| Root | `Makefile` (entry points), `docker-compose.yml`, `RUNNING.md` / `DEVELOPMENT.md` (local workflow), `CHANGELOG.md` (repository-level history — **kept current every increment**), `ARCHITECTURE_BASELINE_V1.md`, `DEVELOPMENT_ROADMAP.md`, audit/migration-plan records. |

## 6. Coding Standards

- **Naming.** Python modules/tables `snake_case`; business codes stored UPPERCASE and normalized on input (supplier `S-XXXXXX`, rate card `RC-XXXXXX`, product/dimension codes `LIKE-THIS`); permission keys `<module>.<entity>.<action>`; wire events `<domain>.<fact>.v<major>`; docs follow STD-0002/0003 (IDs like `CAP-0001`).
- **Module layout.** `models.py` (persistence + module constants) and `service.py` (application service + Pydantic DTOs: `*Command`/`*Input` in, `*View`/`*Page` out). A second service file (e.g. `pricing/matrix.py`) is acceptable when one file would become unwieldy — same module, same boundary.
- **Business objects.** Owned by exactly one module; referenced elsewhere by UUID only. Status machines are explicit verb methods with guards (`submit_for_review`, `approve`, …), not generic setters. Immutable states reject mutation with 409 and a message that names the escape hatch ("create a new version").
- **Value objects.** Realized as validated Pydantic types and normalized scalars (currency codes, QR payloads, half-open ranges) rather than ORM classes — keep validation in the DTO layer and constraints in the DB (`CheckConstraint`) when cheap.
- **Repositories.** The AsyncSession *is* the repository (documented pragmatism). Services encapsulate all queries; routers never query. If a query is needed twice, it becomes a service helper.
- **Domain vs application services.** Pure domain logic (e.g. `backoff_delay`, `_ranges_overlap`) lives as module-level functions — testable without I/O. Application services orchestrate: validate → mutate → audit → publish event, all in the request transaction.
- **Events.** Publish via the injected `Bus` only, with `aggregate_type`/`aggregate_id` set. Map PascalCase domain event names to wire names in a module-level `BUS_EVENTS` dict. Payloads carry ids and facts, not whole objects.
- **Testing.** API-level async tests via `httpx.AsyncClient`; fixtures compose real flows (org → branch → center → supplier → …) — no mocking of internal layers; the in-memory bus (`bus.published`) asserts events; SQLite + inline outbox make the suite infrastructure-free. Meet or exceed the work order's minimum; cover permissions, tenant isolation, validation failure paths, and concurrency rules (CAS) alongside happy paths.
- **Error handling.** Raise the `core/errors.py` hierarchy (`NotFoundError` 404, `ConflictError` 409 for rule violations, `ForbiddenError` 403, `InvalidTokenError` 400, …) — handlers render RFC-9457 problem+json. Never return raw 500s for anticipated conditions; never leak another tenant's existence (use 404).
- **Logging.** `structlog` key-value logging; request id + correlation id bound per request. Log facts (`event_dead_lettered`), never secrets or tokens.
- **Permissions.** Registry entry first (`permissions.py` + role lists), guard second (`require_permission`), test third (viewer-can't-manage). Startup sync (`ensure_system_roles`) picks up new keys automatically.
- **Migrations.** Alembic autogenerate against a scratch DB, then verify `upgrade → downgrade → upgrade`, then lint. Never edit an applied migration; chain is linear.
- **Comments.** Only for constraints the code cannot express (walls like "no calculation here", concurrency reasoning, documented pragmatisms). No narration.
- **Datetimes.** Timezone-aware UTC everywhere; use `as_utc()` before comparing anything read from SQLite; `utcnow()` from `core/db.py`.

## 7. Completed Work (the platform's evolution)

The repository was built in strictly ordered phases — documentation first, platform second, business modules third, pricing fourth. (Full detail: [CHANGELOG](../../CHANGELOG.md).)

1. **Documentation republic (pre-code).** Standards/governance/template suites; the 86-capability Business Capability Model; a quality pass (health report, gap analysis, traceability); the five-layer EA framework with validators; a hygiene pass (navigation, XREF, coverage); and the **Lacteva Collect** product package (PSP-0001…0010: actors, centers, hardware, shift engine, rules R01–R12, event register).
2. **Platform Foundation (M0).** The modular monolith with identity/organization/auth/authz/configuration/audit, infrastructure ports, tenancy, i18n, observability, CI — zero dairy logic, every shortcut marked `TODO(M#)`.
3. **Baseline lock.** Repository audited (health 88/100), migration plan executed, `ARCHITECTURE_BASELINE_V1` established as source of truth with precedence rules; every formal doc references it.
4. **SPRINT-001 Bootstrap.** One-command dev environment; portal and mobile scaffolds with live status screens; Makefile; CI for all three codebases; committed Alembic baseline.
5. **SPRINT-002 Identity & Organization.** Real session security (rotation, theft detection), workspaces/branches/membership/invitations, RBAC wired end-to-end.
6. **SPRINT-003 Collection Centers.** Facility management only: lifecycle, config, operating hours, calendar; first full-stack business slices in portal + mobile.
7. **SPRINT-004 Operational Readiness.** Device registry/assignment/health, operator assignment, and the readiness engine gating operations — mock adapters only.
8. **SPRINT-005 Supplier Platform.** Supplier lifecycle, profiles, documents, banking, m:n center placement, signed QR identity, search, resilient bulk import.
9. **SPRINT-007 Milk Collection Engine.** Readiness-gated sessions; the immutable transaction state machine with snapshot/event-log/metrics; QR/code/phone/manual identification; mock scale/analyzer; pricing left as an explicit placeholder. *(SPRINT-006 was never issued — the numbering gap is historical, not lost work.)*
10. **SPRINT-008A Relay.** The transactional outbox retrofitted *behind* the existing bus port — ~40 publish sites became durable with zero call-site changes; CAS dispatch, retries, DLQ, replay, relay ops API.
11. **Pricing Increment-001 Rate Card Foundation.** The rate card aggregate: five-status review workflow, immutable-once-published, versioning with copied scope, center+product assignment, effective-date overlap rule (one published card per center+product+date).
12. **Pricing Increment-002 Pricing Matrix Foundation.** Configurable quality dimensions as tenant data (FAT is not hardcoded); per product×dimension matrices of half-open `[from, to)` price bands with overlap rejection, dimension bounds, continuity gap reporting; lifecycle riding the rate card (draft-editable → active on publish → archived with card → copied by new versions). **Definitions only — no calculation exists anywhere.**
13. **PRC-003 Pricing Resolution Engine.** Read-side selection: (center, product, date, dimension, reading) → exactly one published card → one active matrix → one band, via a fixed 3-query pipeline with an explicit reusable repository; structured `pricing_no_match` (stage/reason/inputs) and `pricing_integrity` (candidates) exceptions — never a silent choice; platform `Money`/`Quantity` value objects introduced (arithmetic-free until PRC-004). Portal playground + mobile test screen.
14. **PRC-004 Pricing Calculator.** The first monetary calculation: pure deterministic domain service computing gross = unit price × quantity in Decimal only (float factors rejected by type guard), configurable rounding (HALF_UP default / HALF_EVEN / DOWN; request → tenant config → default), complete 4-step trace with exact raw amounts, server-side re-verification of the resolved band (clients send row ids, never prices), `pricing.calculated.v1` through the outbox; stateless — the event is the record. Rules BR-0005…0007 catalogued.

Current test posture: **196 backend tests, 15 Flutter widget tests**, portal build+lint, docs validator + XREF — all green, enforced by CI, verified before every commit.

## 8. Current Roadmap

- **Current milestone (platform):** between M0 and M1 — outbox (M1 item) and clients (M2 scaffolds) landed early by sprint order; remaining M1 hardening: consumer framework, Postgres RLS, Redis caching/throttling, RS256, bootstrap flow, real notification channels.
- **Current platform / product:** Procurement → **Pricing Platform → Rate Management**.
- **PRC-004 (Pricing Calculator) is delivered**; next: **PRC-005 — Bonus Engine** per the epic sequence (bonuses composing on the gross amount, presumably followed by penalties, taxes, simulation, and the full calculator wiring into `milk_collection`'s `awaiting_pricing_engine` placeholder — still unwired by design). Multi-dimension combination policy and publish-time completeness gates (no matrix gaps) also remain open.
- **Pricing epic ahead (names may evolve per work order):** rate tables/versioning/assignment/approval refinements → Formula Engine → Bonus Engine → Penalty Engine → Tax Engine → Simulation → the Pricing Calculator that finally feeds `milk_collection`'s `awaiting_pricing_engine` placeholder.
- **Parallel debt queue:** SPRINT-008B consumer framework; offline sync engine for Flutter (Collect prerequisite); money-precision policy (values are `Float` today by documented decision — the calculation increment must define `Numeric`/rounding); governance ratification (MR-1/MR-3) and founding ADR backfill (B4).
- **Sequencing authority:** [QR-0006](../12-quality/QR-0006-next-work-queue.md) (merged queue), [DEVELOPMENT_ROADMAP](../../DEVELOPMENT_ROADMAP.md) (code), QR-0004 (docs). **User work orders override the queue and are the actual sequencing mechanism** — record any divergence honestly.

## 9. What NOT To Do

1. **Do not redesign the architecture.** The baseline is locked; work orders explicitly forbid it. Extend within the established shapes.
2. **Do not bypass Relay.** All business events go through the injected `Bus` (the outbox). Never call `get_event_bus()` from module code; never publish after commit.
3. **Do not violate DDD boundaries.** Never query another module's tables; go through its service or consume its events. Never put business logic in routers.
4. **Do not duplicate business logic.** One owner per concept. Reuse the CAS pattern, the status-machine pattern, the search/pagination pattern, the QR pattern — do not reinvent them per module.
5. **Do not introduce cloud dependencies unnecessarily.** Local runs on Docker Compose (or SQLite-lite without Docker); tests need no infrastructure at all. AWS enters via `infra/` at M3, behind ports that already exist.
6. **Do not hardcode country- or market-specific rules.** No currency defaults in logic, no locale assumptions, no regulatory constants. Variability is configuration/business data (see: quality dimensions).
7. **Do not create tightly coupled modules.** A module must remain extractable: id references and events only.
8. **Do not mutate the immutable.** Completed transactions, published rate cards, active/archived matrices, historical versions, applied migrations, the outbox audit trail — corrections are new versions, adjustments, or replays.
9. **Do not add permissions, events, or config keys ad hoc.** Registry first, code second — that is what keeps portals, roles, and docs enumerable.
10. **Do not weaken tests to pass.** Fix the code or (with justification recorded) the spec. Never delete history, never force-push, never commit local artifacts (`dev.db`, `.env` — gitignored for a reason).

## 10. AI Instructions (how to work here)

- **Work-order driven.** The user issues explicit work orders (sprints/increments) with scope walls ("NO calculation", "NO hardware") and minimum test counts. Honor the walls literally — building ahead of the order is a defect, not initiative. One standing instruction: **every file-changing turn ends with a Conventional Commit pushed to `origin main`** (`Co-Authored-By: Claude <model> <noreply@anthropic.com>`).
- **Read before writing.** For any task: this file → CHANGELOG (what already exists) → the target module's `models.py`, `service.py`, and *tests* → an adjacent module doing something similar (the codebase is deliberately pattern-consistent; imitate the nearest neighbor).
- **Reason before coding.** Resolve work-order ambiguities *against existing invariants* (e.g. "immutable once published" + "versioned" ⟹ new-version-copies pattern), pick the interpretation that preserves prior increments' rules, and state the decision in the closing summary. If a requirement conflicts with the baseline, say so and record it rather than silently complying or refusing.
- **Verification gates, every time (in order):** backend `ruff check` + `ruff format` + full `pytest`; portal `npm run build` + `npm run lint`; mobile `flutter analyze` + `flutter test`; docs `tools/validate/validate_docs.py` + `tools/xref/generate_xref.py`; migration `upgrade → downgrade → upgrade` round-trip on a scratch DB. Update `CHANGELOG.md` for every increment. All green before commit — no exceptions, no "CI will catch it".
- **Propose changes** to locked material as documents (future ADRs per TPL-0001, baseline V2 via GOV-0002), not as code diffs. Divergences ordered by the user are executed *and recorded* (see REVIEW-NOTES / audit precedent).
- **Maintain consistency** mechanically: same DTO/view naming, same page/screen skeletons per platform, same test fixture chains, same event/audit/permission trio on every mutation. When you find drift, fix it or log it in `docs/12-quality/` — never add a third style.
- **Write engineering summaries** at the end of every increment, exactly as the work order enumerates (architecture, rules, DB, API, screens, events, tests, decisions, remaining work). Lead with what happened; report failures and skipped items plainly; keep honest records of what is pending (the health reports and REVIEW-NOTES set the tone — provenance and assumptions are always disclosed).

## 11. Future Vision

- **Version 1 — Procurement excellence (in progress).** Collection + supplier + readiness + pricing, then settlement: a cooperative runs its entire milk intake digitally, with quality-based payment its farmers can trust. Single-region cloud, portal + online mobile.
- **Version 2 — The operations platform.** Offline-first sync engine; consumer framework powering projections, notifications (SES/SMS/FCM), and search; the full Collect shift engine per PSP specs; inventory, dispatch, and processing capabilities from the CAP model; hardened multi-tenancy (RLS) at real scale.
- **Version 3 — Intelligence & ecosystem.** The AI layer the data model was built for: quality anomaly & adulteration detection, supplier yield forecasting, pricing simulation at scale, agentic workflows (`AGT` artifacts). Marketplace: connecting producers, processors, inputs, and financial services on Lacteva rails. Enterprise: SSO, RS256/key rotation, compliance packs, SLAs, private deployments.
- **Global platform.** Market packs as pure configuration (languages, units, regulatory parameters, payment rails) — the 50-country ambition realized without a single hardcoded country rule, on the same modular monolith until scale forces the seams open, exactly where the module boundaries already are.

---

## Appendix: Known Divergences & Open Items (be honest about these)

| # | Item | Status |
| --- | --- | --- |
| 1 | **No "Constitution" document exists.** Work orders reference one; the de-facto constitution is `ARCHITECTURE_BASELINE_V1` + STD/GOV suites. | Open — either author one or amend references. |
| 2 | **Zero ADRs written** (`docs/03-architecture/adr/` holds only a README; template TPL-0001 exists). The stack was dictated, not decided-by-record. | Open — backfill queue item B4 / MR-2. |
| 3 | Baseline V1 and the CAP suite are content-locked but **pending formal ratification** (MR-1, MR-3 — need a staffed Architecture Board). | Open. |
| 4 | **Pricing epic naming drift**: the pasted epic roadmap said Increment-002 "Rate Tables" / 003 "Rate Versioning"; actual orders delivered 002 "Pricing Matrix Foundation" and named 003 "Pricing Resolution Engine". Work orders supersede the pasted roadmap. | Accepted; recorded here. |
| 5 | **SPRINT-006 never existed** (numbering jumped 005→007). Not lost work. | Historical fact. |
| 6 | **M4 gate overridden by order**: DEVELOPMENT_ROADMAP required Collect-package approval before Collect code; SPRINT-007 was user-ordered across that gate and implemented a *minimal session model*, not the full PSP shift engine. Divergence recorded at the time. | Accepted; shift engine remains future work. |
| 7 | **DEVELOPMENT_ROADMAP.md is stale** (still reads as M0-only, last updated 2026-08-02); CHANGELOG.md is the accurate history. Sequencing reality: outbox (M1) and client scaffolds (M2) landed early; other M1 items pending. | Open — roadmap doc needs a v1.1 refresh. |
| 8 | **Stored money/quality values are `Float`**, not `Numeric` — but the money-precision policy now exists (PRC-004/BR-0005: all *arithmetic* is Decimal via `Decimal(str(x))`, explicit rounding). Residual: column types remain Float; migrate to `Numeric` when a schema change is otherwise due. | Partially resolved (PRC-004). |
| 9 | Platform debt markers: invitation token still returned in the API response (until real delivery, M2), per-request permission DB queries (Redis cache pending), HS256 JWTs, no Postgres RLS, no consumer framework, supplier document upload requires MinIO even in dev-lite. All marked `TODO(M#)` in code. | Open, tracked. |
| 10 | The Increment-002 order introduced a "**Procurement**" platform label above the Pricing Platform — a taxonomy layer not yet reflected in the docs workspace. | Open — minor. |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.3 | 2026-08-03 | Engineering | PRC-004 Pricing Calculator recorded; money precision policy resolved (divergence #8 downgraded); roadmap next = PRC-005 Bonus Engine. |
| 1.2 | 2026-08-03 | Engineering | Business Rules Register (BR-NNNN) added to the engineering philosophy as the source of truth for platform invariants. |
| 1.1 | 2026-08-03 | Engineering | PRC-003 Pricing Resolution Engine recorded (module table, evolution §7 item 13, roadmap next = PRC-004 Pricing Calculator). |
| 1.0 | 2026-08-03 | Engineering (AI context initialization work order) | Initial permanent onboarding guide: vision, philosophies, architecture, structure, standards, history, roadmap, prohibitions, AI working instructions, future vision, divergence register. |
