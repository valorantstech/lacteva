---
id: THREAT-MODEL
title: Threat Model
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [SECURITY, JWT-ROTATION, RLS-GUIDE, SECURITY-CHECKLIST]
baseline: ARCH-BASELINE-V1
---

# Threat Model

What Lacteva is defending, against whom, and with what. Established by SEC-001.

**What is worth stealing here.** Not the software — the *money attribution*. A dairy platform decides what every farmer is owed. The valuable attacks are the ones that change or read that: reaching another cooperative's collection data, granting yourself pricing authority, or replaying a payment. Credential theft matters mainly as a route to those.

Each threat below names its mitigation and the test that proves it.

## 1. Token theft

**Attack.** An access token is captured — from a log, a proxy, a compromised device.

**Mitigation.** Access tokens live 15 minutes and are bound to a server-side session, so logout or password reset kills them immediately rather than waiting out expiry. Tokens are never logged: the audit trail records *events*, never bearer material. Responses are `Cache-Control: no-store`, so a shared proxy cannot retain one.

**Residual risk.** Within the 15-minute window and before revocation, a stolen access token is the user. Shortening the window trades availability for exposure; 15 minutes is the chosen point.

**Proven by** `test_a_revoked_session_stops_working_immediately`.

## 2. Replay attack

**Attack.** A captured refresh token is presented again to mint new credentials.

**Mitigation.** Refresh tokens are single-use with rotation. Presenting a spent token is treated as **theft**, not error: the entire token family is revoked. The platform cannot distinguish the legitimate holder from the thief, so it assumes the worse case and logs both out.

**Residual risk.** A thief who refreshes *before* the legitimate user wins the race and the user is logged out — which is the detection signal, and why `security.token.reuse_detected` is an alert-immediately event.

**Proven by** `test_refresh_replay_is_treated_as_theft`.

## 3. Cross-tenant leakage

**Attack.** A caller reaches another dairy's suppliers, prices, or settlements — via a crafted id, a forgotten filter, or a header claim.

**Mitigation.** Four layers. The token's tenant claim is authoritative and `X-Tenant-ID` cannot override it. Every service filters by tenant. PostgreSQL RLS refuses at the data layer, so a query that forgets its filter returns nothing. Unknown-tenant resources return **404, not 403**, so probing cannot even confirm existence.

**Residual risk.** The platform bypass path (relay, consumers, rebuilds) sees all tenants by design. It is explicit, transaction-scoped, and logged.

**Proven by** `test_a_tenant_header_cannot_override_the_token`, `test_application_level_tenant_isolation_holds`, and the whole PostgreSQL RLS suite.

## 4. Privilege escalation

**Attack.** A viewer grants themselves management rights, or an operator reaches platform-admin operations.

**Mitigation.** Permissions come from a central registry; every guarded route declares one; role management is itself permission-guarded. Platform operations (relay, keys, projections) require platform-staff permissions no tenant role holds. Offline sync reuses the *online* permission, so capturing work on a device is not a side door.

**Detection.** Every denial is audited — an escalation attempt that leaves no trace is one nobody investigates.

**Proven by** `test_a_user_cannot_grant_themselves_a_permission`, `test_permission_denials_are_audited`, `test_offline_never_bypasses_authorization`.

## 5. Key compromise

**Attack.** A signing key leaks; the attacker mints any identity in any tenant.

**Mitigation.** Keys are environment-provisioned, never in source (a test greps for committed PEMs). Retirement is immediate and total: a retired key verifies nothing, killing every token it signed. Rotation is additive, so the *routine* case costs nothing and there is no incentive to defer it.

**Residual risk.** Tokens minted between compromise and retirement are indistinguishable from legitimate ones. The runbook says to assume anything was possible in that window.

**Proven by** `test_a_retired_key_stops_verifying_immediately`, `test_no_secret_material_is_hardcoded_in_source`.

## 6. Database compromise

**Attack.** An attacker obtains database access directly.

**Mitigation.** Honestly: limited. RLS binds the *application*, not a psql session with the owner role. Passwords are argon2 hashes, so credentials do not fall with the data. The audit trail is mirrored to the log stream, so what the attacker did survives even if they wipe the table.

**Residual risk.** Full tenant-data exposure. This is stated in the runbook rather than papered over — encryption at rest protects stolen disks, not a live compromised connection.

## 7. Stolen refresh token

Covered by §2. Worth separating because the *response* differs: reuse detection makes this the one attack the platform actively announces. Treat `security.token.reuse_detected` as an incident, never as noise.

## 8. API abuse

**Attack.** A caller with valid credentials hammers expensive operations — projection rebuilds, consumer replays, template previews — as a denial of service.

**Mitigation.** Per-user and per-IP budgets on exactly those endpoints, with structured `Retry-After`. Business endpoints keep their query budgets (asserted by statement-counting tests), so no single request can become unboundedly expensive.

**Residual risk.** Limits fail open when Redis is down, by choice — see §11.

**Proven by** `test_login_is_rate_limited_with_structured_retry_information`.

## 9. Credential stuffing

**Attack.** Breached credentials from elsewhere are tried in bulk.

**Mitigation.** Login is limited **per-IP and per-identifier**. Per-IP alone misses many hosts against one account; per-account alone misses one host against many accounts. Failures are audited with the source IP, so the pattern is visible even when each individual attempt is under the limit.

**Residual risk.** A slow, distributed attack under both budgets. Detection via audit clustering, not prevention.

## 10. Brute force

**Attack.** Password guessing against one account.

**Mitigation.** The per-account budget (10 per 15 min) makes online guessing hopeless. Argon2 makes offline guessing expensive if hashes ever leak. Responses do not reveal whether an account exists.

**Proven by** `test_a_failed_login_does_not_reveal_whether_the_account_exists`.

## 11. CSRF

**Attack.** A malicious site causes a logged-in user's browser to make authenticated requests.

**Mitigation — and the reasoning, which matters more than the control.** The API authenticates by `Authorization: Bearer` only, never from cookies. There is therefore **no ambient authority** for a cross-site request to abuse: a browser will not attach the token by itself. CORS is an explicit allow-list and never reflects an origin, so a hostile page cannot read a response even if it makes a request.

**The condition on this.** The moment cookie-based authentication is introduced, CSRF defence becomes mandatory. This is recorded as an architectural constraint, not an oversight.

**Proven by** `test_cors_grants_only_configured_origins`, `test_cors_does_not_reflect_arbitrary_headers`.

## 12. Session fixation

**Attack.** An attacker fixes a session identifier or tenant, then rides the victim's authentication.

**Mitigation.** Sessions are server-issued at login and never taken from client input. Tenant comes from the signed token claim, so `X-Tenant-ID` cannot pin a victim into an attacker's tenant. Refresh rotates the session, so an old identifier never survives.

**Proven by** `test_a_tenant_header_cannot_override_the_token`.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by SEC-001. |
