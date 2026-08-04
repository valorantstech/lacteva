---
id: SECURITY
title: Security Architecture
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [BR-REGISTER, JWT-ROTATION, RLS-GUIDE, SECURITY-CHECKLIST, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# Security Architecture

How Lacteva protects tenants, credentials, and money movement. Established by SEC-001 (Phase B).

SEC-001 changed **no business behaviour**. It strengthened trust boundaries around behaviour that already existed: what a token is worth, what the database will hand out, what a caller may do per minute, and what the platform records when someone tries something they should not.

## 1. Trust boundaries

```
   internet
      │   TLS terminates at the load balancer (the only trusted proxy)
      ▼
 ┌──────────────────────────────────────────────────────────┐
 │ security headers · CORS allow-list · rate limits          │  edge
 ├──────────────────────────────────────────────────────────┤
 │ RS256 token verification (kid → registry) · session check │  authentication
 ├──────────────────────────────────────────────────────────┤
 │ RBAC permission guard (denials audited)                   │  authorization
 ├──────────────────────────────────────────────────────────┤
 │ application tenant filter          (defense in depth)     │  application
 ├──────────────────────────────────────────────────────────┤
 │ PostgreSQL row-level security      (authoritative)        │  data
 └──────────────────────────────────────────────────────────┘
```

The important change is the bottom two rows. Tenant isolation used to be a **discipline** — every query remembering its `tenant_id` filter. Disciplines fail silently: one forgotten predicate in one new module is a leak no test necessarily catches. RLS makes the database refuse, so the application filter becomes a second line rather than the only one.

## 2. Authentication

Access and refresh tokens are signed **RS256** with a key drawn from the registry, and each token names its key in the `kid` header. Verification resolves exactly one key — never a fallback, never a guess. Full detail: [JWT-ROTATION.md](JWT-ROTATION.md).

Sessions remain server-side and authoritative: an access token dies with its session, so logout and password reset revoke immediately rather than waiting out the token's lifetime. Refresh tokens are single-use with reuse-as-theft detection — presenting a spent refresh token revokes the whole family, because the platform cannot tell the legitimate holder from the thief and must assume the worse case.

`X-Tenant-ID` is a **hint**, never a grant: a tenant-scoped token's claim always wins.

## 3. Authorization

RBAC is unchanged (registry → `require_permission` guard → test). SEC-001 added one thing: **every denial is audited**. An escalation attempt that leaves no trace is one nobody investigates.

Offline sync reuses the online permission, so capturing work on a device is not a privilege escalation path (BR-0021).

## 4. Data isolation

PostgreSQL row-level security on every tenant-owned table. The request binds `lacteva.tenant_id` with `SET LOCAL` — transaction-scoped, so a pooled connection cannot carry one request's tenant into the next. Platform machinery that is definitionally cross-tenant (relay dispatch, consumers, projection rebuilds) sets `lacteva.bypass_rls` explicitly and logs why. Full detail: [RLS-GUIDE.md](RLS-GUIDE.md).

## 5. Edge protections

**Security headers** on every response including errors: `nosniff`, `DENY` framing, `no-referrer`, a deny-all Permissions-Policy, `default-src 'none'` CSP, and `Cache-Control: no-store` so a shared proxy can never cache one tenant's data for another. HSTS is opt-in because emitting it over plaintext dev teaches browsers a rule the developer cannot retract.

**CORS** is an explicit allow-list of origins, methods, and headers. No wildcards, no origin reflection. Production configuration refuses `*`.

**Rate limits** protect login, refresh, password reset, invitation acceptance, notification preview, projection rebuild, and consumer replay. Credential endpoints are keyed per-IP *and* per-identifier: one host against many accounts (credential stuffing) and many hosts against one account (distributed brute force) are different attacks, and a per-IP budget alone catches only the first.

**Trusted proxy assumption.** Client IPs come from `X-Forwarded-For`, trusted because the deployment contract says only the load balancer sets it. An untrusted proxy in front of the platform would let callers forge their rate-limit identity. This assumption is a deployment requirement, not an implementation detail.

## 6. Secrets

Nothing sensitive is in source. Every secret is environment configuration, and production **refuses to start** on a development default — dev secrets are deliberately obvious sentinels (`dev-secret-change-me`) so a leaked one is recognisable and useless.

| Environment | Keys | Secrets | Notes |
| --- | --- | --- | --- |
| development | ephemeral RSA generated at startup, never written to disk | sentinel defaults | no provisioning step; nothing to leak |
| staging | provisioned `LACTEVA_JWT_KEYS`, rotated on the production schedule | real, distinct from prod | rehearse rotation here |
| production | provisioned, ≥2 keys during rotation | real, injected by the orchestrator | startup validation enforces all of it |

**Future:** AWS Secrets Manager fits behind the same environment contract — a sidecar or entrypoint resolves secrets into the process environment, so no application code changes. Rotation via Secrets Manager then means writing a new `LACTEVA_JWT_KEYS` document and restarting rolling, which the additive registry already tolerates.

## 7. Audit

Security events land in the same immutable audit table as business events, deliberately: an investigator should not have to correlate two stores. Recorded: login success and failure, refresh, reuse detection, logout, password reset request and completion, permission denial, RLS denial, key rotation, rate-limit violation, and security configuration change. Events also go to the log stream, so an attacker who reaches the database cannot erase what already left the host.

Nothing logs a credential, token, or key.

## 8. Failure modes

| Failure | Behaviour | Rationale |
| --- | --- | --- |
| JWKS endpoint unavailable | Platform is unaffected — it verifies from its own registry, not over HTTP. External resource servers degrade. | Discovery is for consumers, not for us |
| Redis unavailable | Rate limits **fail open** (configurable) and the failure is logged | A dairy must not stop accepting milk because a cache is down |
| Rate limiter fails closed (opt-in) | 429 with retry information | For deployments that prefer refusal to permissiveness |
| Signing key missing | Startup fails in prod; dev generates an ephemeral key | A silent fallback to a weaker mode is how platforms ship insecure |
| Unknown `kid` | 401. Never a fallback to another key | Trusting an unnamed key is the forgery path |
| Expired / retired key | 401 immediately | Retirement is the emergency revocation lever |
| Clock skew | ±30 s leeway (`LACTEVA_JWT_LEEWAY_SECONDS`) | Two nodes disagreeing by seconds must not log a farmer out |
| RLS misconfigured (policy absent) | Application filters still apply; the coverage test fails in CI | Defense in depth is the point |
| RLS misconfigured (no tenant bound) | Zero rows — fails **closed** | An unbound session is not a privileged session |

## 9. Rollback

Every hardening step is independently reversible; none requires a data migration.

| Change | Rollback | Cost |
| --- | --- | --- |
| RS256 | `LACTEVA_JWT_ALGORITHM=HS256` + `LACTEVA_JWT_SECRET` | All live sessions invalidated (different signing scheme) |
| Key rotation | Reinstate the previous key document | None if the old key has not expired |
| Emergency key compromise | Mark the key `retired: true` and deploy | Every token it signed dies at once — intended |
| RLS | `alembic downgrade` one revision, or `LACTEVA_RLS_ENABLED=false` to stop binding | None; application filters continue to isolate |
| Security headers | `LACTEVA_SECURITY_HEADERS_ENABLED=false` | Browsers may cache HSTS until `max-age` elapses |
| Rate limiting | `LACTEVA_RATE_LIMIT_ENABLED=false` | Abuse protection removed |

HSTS deserves emphasis: it is the one change a browser will honour *after* you roll back. Enable it only when TLS is permanent for the domain.

## 10. Known limits

- **RS256, not EdDSA.** RS256 is universally supported by the resource servers and gateways a dairy integrates with. Ed25519 is faster and smaller; the registry is algorithm-shaped and could carry it later.
- **No per-request permission cache.** Authorization still costs one indexed lookup per guarded request; Redis caching is Phase B work.
- **The fixed-window limiter admits burst-at-boundary.** Twice the budget can pass across a window edge. Acceptable for abuse control; a sliding window would cost more per request than the precision is worth.
- **Rate limits are per-process in dev.** The memory backend cannot see other workers; production uses Redis.
- **No CSRF tokens, by design.** The API is bearer-authenticated and never accepts credentials from cookies, so there is no ambient authority for a cross-site request to abuse. Introducing cookie auth would make CSRF defence mandatory.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by SEC-001. |
