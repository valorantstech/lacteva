---
id: API-0001
title: Platform Core REST API
type: api
status: Approved
version: "1.1"
owner: Architecture Board
created: 2026-08-07
last-updated: 2026-08-07
related: [SECURITY, RLS-GUIDE, DEPLOYMENT, DBD-0001]
baseline: ARCH-BASELINE-V1
---

# API-0001 — Platform Core REST API

The conventions every endpoint follows. Established by **API-001**, which reviewed all 177 operations as if preparing a public SaaS release.

**The OpenAPI document is authoritative for schemas** — `GET /openapi.json`, or `/docs` outside production. This document is authoritative for *semantics*: the rules a schema cannot express, and the reasons behind them. Where they disagree, the OpenAPI wins on shape and this wins on meaning.

Until now the platform had 177 endpoints and no API document, against this layer's own rule that an undocumented endpoint is an incident. This closes that.

---

## 1. Surface

| | |
| --- | --- |
| Operations | 177 across 155 paths |
| Methods | 87 POST, 73 GET, 9 DELETE, 8 PUT |
| Base path | `/v1` — a URI major version, additive-only within it |
| Media type | `application/json`; errors are `application/problem+json` |
| Public (unauthenticated) | 7 operations, enumerated in §3 |

---

## 2. Errors — RFC 9457 problem details

Every error, from every endpoint, has one shape:

```json
{
  "type": "https://docs.lacteva.example/errors/conflict",
  "title": "conflict",
  "status": 409,
  "detail": "A published rate card cannot be modified.",
  "extra": { "rate_card_id": "…", "status": "published" }
}
```

- **`type`** and **`title`** are stable. Branch on these.
- **`detail`** is translated into the caller's locale. Display it; **never branch on it**.
- **`extra`** carries machine-readable specifics when the error class has any — the conflicting field, the pricing-resolution stage that failed, the retry budget.

| Status | Meaning | Retry? |
| --- | --- | --- |
| 401 | No credentials, or a token that does not verify | Only after re-authenticating |
| 403 | Authenticated, lacking the permission | No |
| 404 | No such resource **in this tenant** | No |
| 409 | Contradicts current state — duplicate value, or a refused transition | **No.** An unchanged retry fails identically |
| 422 | Validation failure | No |
| 429 | Rate limited | **Yes**, after `Retry-After` |
| 5xx | Platform fault | Yes, with backoff |

**A resource belonging to another tenant is a 404, never a 403.** A 403 would confirm that the id exists, which is itself a cross-tenant disclosure.

**These are now published.** Before API-001 the OpenAPI document declared exactly one non-2xx response — FastAPI's automatic 422 — so every generated client treated an error body as an unknown shape. The declarations are applied centrally by three mechanical rules (`main._publish_error_contract`): every `/v1` operation can return 401/403/422/429; an operation with a path parameter can return 404; an operation that mutates can return 409.

---

## 3. Authentication and tenancy

Bearer tokens, RS256, verified against a named key from the registry (`kid`, with JWKS at `/v1/.well-known/jwks.json`).

**The token is the authority on tenant.** A tenant-scoped token cannot be re-scoped by the `X-Tenant-ID` header — the header is a bootstrap path for *platform-level* principals only. This is asserted by test, because a client-supplied tenant boundary is not a boundary.

These 7 operations are unauthenticated, and the list is closed by test — a new public endpoint must be added there deliberately:

`POST /v1/auth/register` · `POST /v1/auth/token` · `POST /v1/auth/refresh` · `POST /v1/auth/password-reset/request` · `POST /v1/auth/password-reset/confirm` · `POST /v1/invitations/accept` · `GET /v1/.well-known/jwks.json`

Everything else is permission-guarded. Permissions are checked per route, and a denial is recorded as a security event.

---

## 4. Lists, pagination, filtering, sorting

**The rule:** a list whose length grows with business volume is **paginated**; a list bounded by structure — a tenant's workspaces, a supplier's bank accounts, the quality dimensions — may be a bare array. Ceremony on a fixed-size list buys nothing.

Paginated responses are uniform:

```json
{ "items": [...], "total": 1234, "limit": 20, "offset": 40 }
```

**Page size is bounded, and an out-of-range value is rejected — not clamped.** This was a real defect: services clamped silently at 100, so a client paginating with `limit=1000` believed it had read 1000 records, received 100, and then jumped to `offset=1000` — **skipping 900 rows it never saw**. Silent clamping turns a page-size mistake into missing data. The bound is now declared on the route, published in OpenAPI, and violations get 422.

| Endpoint class | Default | Maximum |
| --- | ---: | ---: |
| Business lists | 20 | 100 |
| Collection sessions | 50 | 200 |
| Operator lists (`/v1/_*`) | 50 | 200 |
| Audit | 100 | 500 |

**Filtering** is per-endpoint and explicit — `status`, `center_id`, `supplier_id`, date ranges. There is no generic query language, deliberately: a filter that can express arbitrary predicates is a filter that can express an expensive one.

**Sorting is not client-controllable.** Every list has one defined order — newest first for time-series, name for reference data. This is a known limitation (§8), not an oversight: sortable columns need indexes, and an unindexed sort on a table this size is a way to take the platform down from a query string.

---

## 5. Retry safety and idempotency

| Method | Safe to retry | Why |
| --- | --- | --- |
| `GET` | Yes | No side effects |
| `PUT` | Yes | Idempotent by construction |
| `DELETE` | Yes | Deleting a deleted thing is 404, not damage |
| **`POST` creating a resource** | **Only with `Idempotency-Key`** | Otherwise it creates a second one |
| `POST` transitioning state | Yes, in effect | The CAS guard refuses the second attempt with 409 — the state moved once |

**State transitions are protected by construction.** `POST /v1/payments/{id}/complete` twice returns 200 then 409: the transition is compare-and-set against the expected current state, so a retry cannot double-apply. This is why transitions return **200** rather than 201 — they act on an existing resource.

**Creation is the exposed case, and paying twice is the worst outcome this API has.** `POST /v1/payments` accepts an **`Idempotency-Key` header**: a repeat returns the payment the first request created, unchanged. A mobile client on a village connection cannot distinguish a lost response from a lost request, and this platform is explicitly built for that network.

### The framework (IDM-001)

**`Idempotency-Key` works on every POST, PUT and PATCH.** Send one and the operation becomes retry-safe; omit it and nothing changes, so the capability costs nothing until used.

| Situation | Response |
| --- | --- |
| First request | Runs normally |
| Retry after it completed | The **original response**, verbatim — same status, same body, plus `Idempotent-Replay: true` |
| Retry while the first is still running | `409` — the operation is happening, and inventing an answer would be worse than asking you to wait |
| Same key, **different body** | `400` — the key identifies a request; replaying the first response would silently discard this one |
| Key after the retention window | Treated as new. Retention is 24 hours by default |

**Keys are scoped to your tenant**, so two organizations can use the same key without colliding — which matters, because a client library that derives keys from a request hash makes collisions certain rather than unlikely.

**The record shares the operation's transaction.** The reservation, the business write and the stored response commit together or not at all, so a crash cannot leave a key claiming an effect that never happened. That is the difference between a framework that helps a retrying client and one that strands it.

Keys are 1–128 characters. Use something unguessable and unique per logical operation — a UUID per user action, generated once and reused across that action's retries. Do **not** derive it from the body alone: two genuinely different operations can have identical bodies.

**Payment keeps its own `idempotency_key` body field**, and it means something different: the header dedups an *HTTP request*, the field dedups a *business intent* — that payment, ever, even across two genuinely different requests. Both are useful; neither replaces the other.

---

## 6. Concurrency

Optimistic locking is **internal, not exposed**. Every lifecycle transition is CAS-guarded against the expected current state, so two clients racing a transition produce one success and one 409 — the platform never silently applies both.

What is *not* protected is a concurrent field update: two clients editing a supplier's profile are last-writer-wins, and neither is told. There is no `ETag`/`If-Match` on any endpoint. For the current single-operator-per-center reality this has not bitten; for a public API with integrations it should be added. §8.

---

## 7. Other conventions

**Status codes.** 201 for creation with the resource in the body. 200 for reads and state transitions. 204 for deletions, with no body. Operator endpoints under `/v1/_*` may return 200 with a report of what they did, because "what was reset" is the useful part.

**Audit.** Every state-changing operation writes an immutable audit record carrying the actor, the tenant, and the correlation id. Reads are not audited — auditing reads on a collection-heavy platform would produce more audit rows than business rows.

**Correlation.** Send `X-Request-ID` or one is generated. It is returned on the response, bound into every log line, persisted on every event the request produces, and rebound by the consumer that later handles that event — so one id spans the request and all its asynchronous consequences (BR-0024).

**Rate limits.** Applied per IP and per identifier on credential and expensive endpoints. 429 carries `Retry-After`. The limiter fails **open** by design: an unavailable limiter must not take the platform down.

**Uploads** are base64 in a JSON body, capped at 5 MiB per document; nginx caps the request at 25 MB. **Downloads** are presigned object-storage URLs with a short expiry, issued only after the tenant-scoped resource check. There are **no streaming endpoints and no websockets** — a test asserts the latter, so the first one added has to design its tenant binding, because a socket outlives the request that authenticated it.

**Caching.** No endpoint sets cache headers, and nginx marks `/v1/` uncacheable. This is deliberate: responses are tenant-scoped, and a cache that does not understand that is a cross-tenant leak with extra steps.

---

## 8. Known limitations

Each is a decision with a reason, not an omission:

| # | Limitation | Why it is acceptable now | What would change it |
| --- | --- | --- | --- |
| 1 | ~~No general idempotency~~ — **closed by IDM-001**. Residual: the framework covers HTTP retries, not two genuinely distinct requests expressing the same intent. Only payment has intent-level dedup | Intent-level dedup needs a domain key per resource, which is a per-endpoint decision, not a platform one | A domain uniqueness rule per resource, where duplicates would actually cost something |
| 2 | **No `ETag`/`If-Match`** | Lifecycle transitions are CAS-guarded; only free-field edits race, and today one operator edits at a time | Third-party integrations, or concurrent portal editing |
| 3 | **No client-controlled sorting** | Every list has a sensible fixed order; an unindexed sort is a way to take the platform down from a query string | Add per-endpoint allow-lists backed by real indexes |
| 4 | **No cursor pagination** | Offset is correct and simple at current volumes | Deep offsets on the transaction table — `OFFSET 100000` scans 100,000 rows |
| 5 | **No bulk/batch endpoints** except supplier import | The offline sync path already batches the one operation that needs it | Integration partners writing at volume |
| 6 | **No cache headers on reference data** | Small and rarely read | Measured load on `/v1/quality-dimensions` and similar |
| 7 | **No API-level request timeout** | nginx caps at 75s and PostgreSQL at 30s | A slow endpoint that should fail faster than either |

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-07 | Architecture Board | IDM-001: `Idempotency-Key` documented as a platform capability on every mutation; §8.1 closed. |
| 1.0 | 2026-08-07 | Architecture Board | Established by API-001. Error contract published, page sizes bounded and validated, `Idempotency-Key` on payment creation, conventions recorded. |

## Tenant lifecycle endpoints (PROD-001)

| Method | Path | Permission | Notes |
| --- | --- | --- | --- |
| `GET` | `/v1/tenant-data/export` | `organization.data.export` | Every row the platform holds for the caller's tenant, as portable JSON. Audited. |
| `GET` | `/v1/tenant-data/offboarding-plan` | `organization.data.delete` | Non-destructive. Returns per-table treatment, row counts, and the exact confirmation string required. |
| `POST` | `/v1/tenant-data/offboard` | `organization.data.delete` | Irreversible. Body `{"confirmation": "<organization name>"}`. |

**The tenant is never a parameter.** It comes from the authenticated
principal, so there is no request shape that can name another tenant — a
stronger guarantee than validating that a supplied id matches.

`organization.data.export` and `organization.data.delete` are deliberately
separate from `organization.manage`: exporting every record, and irreversibly
offboarding, are not the same authority as renaming a branch.

## Receipt rendering (PROD-001)

`GET /v1/receipts/{id}/download?format=pdf` now returns **`application/pdf`**
with real PDF bytes. `GET /v1/receipts/{id}/render?format=pdf` returns JSON
with `body` base64-encoded and a new `encoding` field (`"text" | "base64"`), so
a client never infers the encoding from the content type.

`placeholder` is `false` for PDF from this release. Receipts generated before
PROD-001 render without the organization name, center name, quantity and rate
columns — those fields are copied at generation and are not backfilled,
because re-deriving a frozen artifact from a world that has since changed is
what BR-0020 forbids.
