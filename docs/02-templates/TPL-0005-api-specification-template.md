---
id: TPL-0005
title: API Specification Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0005 — API Specification Template

> Template guidance: Copy everything below the rule into `docs/06-api/API-NNNN-<short-title>.md`. This document is the **human-readable contract**; the machine-readable OpenAPI file lives beside it (`assets/API-NNNN-openapi.yaml`) and the two MUST stay in sync — the OpenAPI file is authoritative for schemas, this document for semantics. API versioning follows [STD-0004 §5](../00-standards/STD-0004-versioning-strategy.md).

---

```yaml
---
id: API-NNNN
title: <API name>
type: api
status: Draft
version: "0.1"
owner: <owning team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<SRS-IDs>, <DBD-IDs>, <EVT-IDs>]
---
```

# API-NNNN — \<API Name\>

## 1. Overview

- **Purpose:** \<what this API lets consumers do, one paragraph\>
- **API major version:** v1
- **Audience:** Public / Partner / Internal
- **Base path:** `/v1/<resource>`
- **Owning service:** \<service name, links SRS\>
- **OpenAPI source:** [`assets/API-NNNN-openapi.yaml`](assets/API-NNNN-openapi.yaml)

## 2. Consumers

| Consumer | Use | Contact Team |
| --- | --- | --- |
| \<who calls this\> | \<why\> | \<team — required approver for breaking changes\> |

## 3. Conventions

> Template guidance: Only deviations from platform-wide API conventions go here; otherwise state "Follows platform API conventions (ADR-XXXX)".

- **Authentication:** \<mechanism, token type, required scopes\>
- **Tenancy:** \<how tenant context is carried and enforced; requests MUST be scoped to the caller's tenant\>
- **Pagination:** \<cursor/offset, parameter names, limits\>
- **Errors:** \<error envelope format; link shared schema\>
- **Idempotency:** \<idempotency-key support for unsafe methods\>
- **Rate limits:** \<limits and headers\>

## 4. Resources and Operations

> Template guidance: One subsection per resource. Semantics prose here; full schemas in OpenAPI. Repeat the operation block per endpoint.

### 4.1 \<Resource name\>

\<what this resource represents; link the domain model entity (DOM-ID)\>

#### `<METHOD> /v1/<path>`

- **Purpose:** \<one sentence\>
- **Authorization:** \<required role/scope\>
- **Request:** \<key parameters/fields and their semantics\>
- **Response:** `200` \<shape summary\>; errors: `400` \<when\>, `403` \<when\>, `404` \<when\>, `409` \<when\>
- **Notes:** \<idempotency, side effects, emitted events (EVT-IDs)\>

**Example**

```http
POST /v1/milk-collections
Content-Type: application/json

{ "<field>": "<value>" }
```

```json
{ "<field>": "<value>" }
```

## 5. Data Semantics

| Field | Meaning | Unit / Format | Nullable | Notes |
| --- | --- | --- | --- | --- |
| \<field\> | \<precise meaning per glossary\> | \<ISO 8601, SI unit…\> | Yes/No | \<caveats\> |

## 6. Non-Functional Contract

| Aspect | Commitment |
| --- | --- |
| Availability | \<SLO\> |
| Latency | \<p99 target under stated load\> |
| Payload limits | \<max sizes\> |

## 7. Versioning and Deprecation

- **Compatibility promise:** additive changes only within v1, per STD-0004 §5–6.
- **Deprecation process:** \<notice period, headers, sunset dates, consumer sign-off\>

## 8. Changelog of Contract Changes

> Template guidance: Contract-affecting changes only, most recent first — this is what consumers audit.

| Date | API Change | Breaking? | Doc Version |
| --- | --- | --- | --- |
| \<date\> | \<change\> | Yes/No | \<version\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
