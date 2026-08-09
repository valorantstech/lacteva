---
id: SECURITY-CHECKLIST
title: Security Checklist and Runbook
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [SECURITY, JWT-ROTATION, RLS-GUIDE]
baseline: ARCH-BASELINE-V1
---

# Security Checklist and Runbook

Pre-production gate, operational runbook, and incident response for the Lacteva platform. Established by SEC-001.

## 1. Pre-production checklist

Nothing here is advisory. A "no" blocks the deployment.

### Configuration

- [ ] `LACTEVA_ENV=prod` — this alone activates the startup validator that refuses development credentials.
- [ ] `LACTEVA_JWT_KEYS` provisioned with at least one signing key; `LACTEVA_JWT_ALGORITHM=RS256`.
- [ ] `LACTEVA_MINIO_SECRET_KEY` set to a real secret.
- [ ] `LACTEVA_CORS_ORIGINS` names exact portal origins. No `*`, no empty entry.
- [ ] `LACTEVA_DEBUG=false`.
- [ ] `LACTEVA_HSTS_ENABLED=true` — **only** once TLS is permanent for the domain.
- [ ] `LACTEVA_RATE_LIMIT_BACKEND=redis` and Redis reachable (the memory backend cannot see other workers).
- [x] `LACTEVA_RATE_LIMIT_FAILURE_POLICY` decided: **`degrade`** (SEC-003/F-06). `fail_open` is refused in prod. Override only with a written reason.

### Database

- [ ] Migrations applied through the RLS revision.
- [ ] `SELECT relname FROM pg_class WHERE relrowsecurity AND NOT relforcerowsecurity;` returns **no rows** — a policy that is enabled but not forced protects nothing from the application's own role.
- [ ] The application's database role is **not** superuser and does not hold `BYPASSRLS`.
- [ ] Backups verified by an actual restore, not by the backup job exiting zero.

### Verification

- [ ] `GET /.well-known/jwks.json` returns the expected kids and no private material.
- [ ] `/docs` is absent (disabled in prod).
- [ ] Security headers present on a real response, including a 401.
- [ ] A deliberate burst against `/v1/auth/token` returns 429 with `Retry-After`.
- [ ] The `row-level-security` CI job passed and did **not** skip.

### Access

- [ ] Private key material exists only in the secret store — never in git, CI logs, or a ticket.
- [ ] Operator access to the secret store is enumerated and time-bound.
- [ ] Rotation rehearsed in staging within the last quarter.

## 2. Operational runbook

### Quarterly

- Rotate signing keys ([JWT-ROTATION.md](JWT-ROTATION.md) §2).
- Review the audit trail for `security.permission.denied` clusters — repeated denials against one permission usually mean either an attack or a role that is wrong.
- Re-run the checklist above.

### On staff change

- Any operator with key or secret-store access departing triggers an **immediate** key rotation, not a scheduled one.

### Monitoring signals worth alerting on

| Signal | Threshold | Likely meaning |
| --- | --- | --- |
| `security.login.failed` per IP | > 20 / 5 min | Brute force |
| `security.login.failed` per account | > 10 / 15 min | Credential stuffing |
| `security.token.reuse_detected` | any | **Refresh token theft — investigate immediately** |
| `security.permission.denied` per user | > 10 / min | Escalation probing or a broken client |
| `security.rate_limit.exceeded` | sustained | Abuse, or a client with no backoff |
| `rate_limiter_unavailable` log | any | Redis down; limits are failing open |
| 401 rate | sudden spike | Key misconfiguration after a deploy |

## 3. Incident response

### A refresh token was stolen (`security.token.reuse_detected`)

The platform already revoked the family automatically — that is what the detection does. Then:

1. Identify the user and session from the audit record.
2. Review that user's activity around the event.
3. Force a password reset if the account itself may be compromised.
4. Note that the automatic revocation means the *legitimate* user was also logged out. That is intended: the platform cannot distinguish them, and the safe assumption is theft.

### A signing key was compromised

1. Emergency rotation immediately ([JWT-ROTATION.md](JWT-ROTATION.md) §3) — retire the key, publish a replacement.
2. Expect every client to re-authenticate. Communicate before, if the timing is yours to choose.
3. Rotate the secret-store credential that exposed the key. Rotating only the key leaves the door open.
4. Audit for tokens minted by the compromised key between compromise and retirement — assume anything is possible in that window, including cross-tenant access.

### Suspected cross-tenant leakage

1. Confirm from the data, not the report: which rows, which tenants, which endpoint.
2. Check whether RLS was live: `relrowsecurity AND relforcerowsecurity` on the table, and whether the request bound a tenant.
3. If a policy was missing, the coverage test should have failed in CI — find out why it did not.
4. If RLS was live and the leak still happened, the path used the bypass. Every bypass logs its reason; find it.

### The database was compromised

RLS does not protect against a compromised database — an attacker with the database has the data. Assume total tenant-data exposure and act accordingly. What the platform still gives you: an immutable audit trail replicated to the log stream, so what the attacker *did* survives even if they wipe the table.

### Redis is down

Rate limits degrade to the process-local counter and log `rate_limiter_degraded` (SEC-003/F-06). The platform stays up and collection continues, and abuse protection stays on at `limit x worker count`. Treat as urgent-but-not-emergency: the budget is looser than intended until Redis returns.

## 4. What this platform does not defend against

Stated plainly so nobody assumes otherwise:

- **A compromised application host.** Process memory holds signing keys and decrypted data.
- **A malicious insider with database access.** RLS binds the application, not a psql session with the owner role.
- **Supply-chain compromise of a dependency.** Pinned versions and lockfiles only narrow the window.
- **Social engineering of an operator.** The strongest key rotation in the world does not survive someone being asked nicely for the private key.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by SEC-001. |
