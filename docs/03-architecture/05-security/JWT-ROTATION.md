---
id: JWT-ROTATION
title: JWT Key Rotation Procedure
type: reference
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-05
related: [SECURITY, SECURITY-CHECKLIST]
baseline: ARCH-BASELINE-V1
---

# JWT Key Rotation Procedure

Operational runbook for the signing keys behind every Lacteva token. Established by SEC-001.

**The property that makes this safe: rotation is additive.** A new key is published alongside the old one, becomes the signer, and the old key keeps verifying until its tokens expire naturally. No session is invalidated, no user is logged out, and no coordinated restart is required.

## 1. The registry

`LACTEVA_JWT_KEYS` is a JSON array. Each entry:

| Field | Meaning |
| --- | --- |
| `kid` | Stable identifier. Appears in every token header and in the JWKS document. |
| `public_pem` | Public half. Required. |
| `private_pem` | Private half. Omit for verify-only keys — a predecessor can keep verifying without the platform ever holding its private material again. |
| `activates_at` | When this key may sign. A future value **schedules** a rotation. |
| `expires_at` | When it stops verifying. |
| `retired` | `true` kills it immediately — the emergency lever. |

Rules the registry enforces:

- The **current** signing key is the most recently activated key that can sign.
- Every unexpired, unretired key **verifies**.
- Retired and expired keys verify nothing and are withheld from JWKS.

## 2. Scheduled rotation (the normal case)

Rotate every 90 days, or whenever an operator with key access leaves.

**Step 1 — generate.** On a trusted host:

```bash
uv run python -c "
from platform_core.core.keys import generate_keypair
import json
k = generate_keypair(kid='prod-2026-11')
print(json.dumps({'kid': k.kid, 'public_pem': k.public_pem, 'private_pem': k.private_pem}))
"
```

Never commit this output. It goes straight into the secret store.

**Step 2 — publish alongside.** Extend `LACTEVA_JWT_KEYS` with the new key and an `activates_at` a few minutes ahead. Keep the old key with **no** `expires_at` yet. Deploy rolling.

**Step 3 — verify before it signs.** `GET /.well-known/jwks.json` must list both kids. `GET /v1/_security/keys` must show the old key `can_sign: true` and the new one `pending`.

**Step 4 — let it take over.** At `activates_at` the new key signs automatically. Confirm a fresh login carries the new `kid`. Existing sessions are untouched — that is the point.

**Step 5 — age the old key out.** Set the old key's `expires_at` to **now + the refresh-token TTL** (14 days by default). Earlier would strand valid refresh tokens; later leaves a compromised-key window open longer than necessary.

**Step 6 — remove.** After `expires_at` passes, drop the entry and drop the private material from the secret store.

## 3. Emergency rotation (key compromise)

Skip the graceful path. Every token the key signed must die.

1. Add `"retired": true` to the compromised entry and add a fresh key with `activates_at` in the past.
2. Deploy immediately.
3. Every token signed by the retired key now fails with 401; clients re-authenticate.
4. Record a `security.key.rotated` audit entry with the incident reference.
5. Rotate the secret-store credentials that exposed the key, not just the key.

Expect a login storm. This is the correct trade: a compromised signing key can mint any identity in any tenant.

## 4. Rolling back a rotation

If a new key is bad (wrong PEM, unreachable secret), remove its entry and redeploy. The previous key resumes signing because it is once again the newest key that can sign. Nothing else changes.

## 5. What can go wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| Startup fails: "no signing key is active" | Every key is expired, retired, or not yet activated | Check the windows; install a key with `activates_at` in the past |
| 401s spike after a deploy | A key was removed while its tokens were live | Restore the entry until `expires_at` has genuinely passed |
| New tokens still carry the old kid | The new key's `activates_at` has not arrived, or it has no `private_pem` | Check `GET /v1/_security/keys` |
| JWKS missing a key | It is retired or expired | Correct — never advertise a key that must not be trusted |

## 6. Environments

| | Keys | Rotation |
| --- | --- | --- |
| development | Ephemeral, generated per process, never on disk | Restarting rotates; nothing to manage |
| staging | Real, provisioned | **Rehearse here first** — a rotation drill in staging is the only cheap one |
| production | Real, ≥2 during rotation | Scheduled quarterly; emergency on demand |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Established by SEC-001. |
