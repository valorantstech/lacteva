---
id: DEMO-008-FINAL
title: DEMO-008 — Authentication, RBAC & Permission Architecture
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-12
last-updated: 2026-08-12
related: [DEMO-007-FINAL, DEMO-006-FINAL, STD-0007, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-008 — Authentication, RBAC & Permission Architecture

The work order asked to *replace the current hard-coded admin/manager
authorization model with a production-ready, database-driven system*.

**There was no hard-coded authorization model to replace.** Authorization has
been database-driven since this platform was built. The honest deliverable was
therefore narrower and, in one place, more serious than the brief assumed: five
real gaps, one of which was a live security defect and one of which was a data
integrity defect that only appeared when the deployed system was inspected.

---

## 1. What already existed

Read before anything was written.

| Capability | Where | State |
|---|---|---|
| Role / permission persistence | `role`, `role_permission`, `user_role` | present |
| Permission resolution | `PermissionEngine.effective_permissions()` — a DB query per request | present |
| Route enforcement | `require_permission()` on every protected route | present |
| Denial as a security event | `record_security_event(PERMISSION_DENIED)` + `AUTHZ_DENIALS` metric | present |
| Permission registry | 44 keys; an unregistered key is refused with 409 | present |
| System-role seeding | `ensure_system_roles()` at startup | present, **not race-safe** |
| Organization membership | `membership` with `status` | present, **status unenforced** |
| Tenant isolation | contextvar + PostgreSQL RLS, 404 not 403 | present |
| Permission-aware navigation | `can(session, permission)` per entry | present |
| Session endpoint | `GET /v1/auth/me` | present, **thin** |
| Password hashing, session expiry, revocation | `AuthService`, `AuthSession` | present |

Nothing in the codebase branches on a role name to decide access. The only
role strings in `src/` were the seed definitions themselves.

---

## 2. The five real gaps

1. **A suspended member kept working.** (§15.9 — a security defect.)
2. **The eight named roles did not exist.** (§3.)
3. **No centre-level scoping.** (§7.)
4. **No way to READ the roles**, which is why the portal hard-coded them. (§10.)
5. **`/v1/auth/me` carried no organization, membership or role.** (§13.)

And one found by running the deployed platform rather than reading it:

6. **System roles could be duplicated, and the constraint could not stop it.**

---

## 3. Authentication architecture

Unchanged in substance, extended in two places. Login verifies a hashed
password, refuses unknown-user and wrong-password identically (no oracle),
checks `user.is_active` and the membership, then issues an access/refresh pair
bound to an `AuthSession` row. Logout and password reset revoke the session, so
an access token dies with it rather than living out its expiry.

Added:

* `user_account.last_login_at`, stamped on the one path that proves a
  credential was accepted. A refresh does **not** update it — a token renewing
  itself is not the person coming back.
* **Membership re-checked on every request** (§4 below).

The portal holds no token: it goes same-origin to `/api/proxy`, which attaches
an HttpOnly, Secure, SameSite=Strict cookie server-side. Verified in a real
browser: `document.cookie` is empty to script, and neither storage holds a JWT.

**MFA/OTP readiness.** Nothing in the User → Membership → Role → Permission
chain encodes *how* the credential was proved. A second factor becomes another
check inside `AuthService.login` before the session is issued, and an
`AuthSession` column recording that it happened. No relationship needs to move.

---

## 4. The security defect: suspension did nothing

`Membership.status` was checked at **login** and never again.

`AuthService.login` refused a suspended member; `AuthService.refresh` checked
`user.is_active` but **not** membership. So suspending someone changed nothing
until their access token expired — and their refresh token kept minting new
ones indefinitely. The suspension was a note in a table.

Fixed in `get_current_principal`, beside the `user.is_active` check that
already had this guarantee:

```python
if token_tenant is not None:
    if not await MembershipService(session).is_active_member(user.id, token_tenant):
        AUTH_FAILURES.labels("membership_inactive").inc()
        raise UnauthorizedError()
```

A suspension now takes effect on the member's **very next request**. The test
issues a token while the member is in good standing, suspends them, and asserts
that the same token is refused with 401.

`POST /v1/members/{user_id}/status` was added because the status column existed
from the beginning and nothing could write it — suspension was a database
operation, which meant in practice that it never happened. It is audited.

---

## 5. The integrity defect: duplicate system roles

Found by calling `GET /v1/authz/roles` on the deployed platform, which listed
`platform-admin`, `tenant-admin` and `tenant-viewer` **three times each**.

`role` carries `UNIQUE (tenant_id, name)`, and every system role has
`tenant_id IS NULL`. In SQL, NULL is not equal to NULL — so a composite unique
constraint containing a NULL never conflicts. The constraint that looked like
it enforced "one system role per name" enforced nothing at all for system
roles. `ensure_system_roles` selects-then-inserts, which is idempotent in
isolation and useless under concurrency: two workers starting together both
select nothing, both insert, and the database accepts both. Three duplicates
was three racing starts.

**Not a security hole** — effective permissions are the union over a user's
grants, and every copy carried identical permissions. But it was a latent
hazard: had the registry grown while grants were spread across copies, two
users holding "the same" role would have had different access.

Fixed in migration `b7c2e94d1a55`: merge each duplicate set into the copy the
system had actually been using (repointing grants, dropping those that would
collide), then add a **partial unique index** — the only construct that
actually enforces it:

```sql
CREATE UNIQUE INDEX uq_role_system_name ON role (name) WHERE tenant_id IS NULL
```

`ensure_system_roles` now survives losing the race instead of relying on not
having one. The regression test inserts a second `tenant-admin` and asserts the
database refuses it. Verified live after deployment: no duplicates, index
present, **13 users still hold roles — no grant was lost**.

---

## 6. Authorization architecture

```
User ──► Membership (status, per organization)
     └──► UserRole (grant: role + tenant + OPTIONAL centre)
              └──► Role ──► RolePermission ──► permission key
                                                   └──► require_permission() on the route
```

Every request resolves: who (session → user), where (token tenant, authoritative
over any header), is the membership active, which grants, which permissions,
does the resource belong to the tenant (RLS), and — new — is the centre in
scope.

**Permission naming was deliberately left alone.** The work order lists keys
like `centre.view`; the registry spells them `<module>.<entity>.<action>`, e.g.
`collection.center.read`. Every guard, every seeded grant and every test in the
tree depends on those exact strings. Renaming would have been a cosmetic change
that broke DEMO-001 through DEMO-007 on the way past, so the eight roles are
composed from the existing keys and the capability mapping is documented in §8.

---

## 7. Roles created

Eight, seeded idempotently alongside the three that already existed.

| Role | Permissions | Intent |
|---|---|---|
| `PLATFORM_SUPER_ADMIN` | `*` | platform staff |
| `ORGANIZATION_ADMIN` | 41 | everything inside one organization |
| `ORGANIZATION_MANAGER` | 18 | runs operations; administers neither people nor prices |
| `CENTRE_MANAGER` | 9 | one centre's operation |
| `COLLECTION_OPERATOR` | 6 | records collections; administers nothing |
| `FINANCE_OFFICER` | 11 | settlements and payments, but cannot finalize |
| `FINANCE_MANAGER` | 14 | officer + `settlement.finalize`, `payment.cancel`, `receipt.manage` |
| `AUDITOR` | 18 | reads everything, changes nothing |

`tenant-admin`, `tenant-viewer` and `platform-admin` are unchanged — every
existing demo user, invitation and test holds one of them.

---

## 8. Role → permission mapping

Composed entirely from registered keys. The capability names in the work order
map onto them as follows (a representative sample; the full sets are in
`modules/authz/permissions.py`):

| Work order | This registry |
|---|---|
| `centre.view` / `centre.create` | `collection.center.read` / `collection.center.manage` |
| `supplier.view` / `supplier.create` | `supplier.read` / `supplier.manage` |
| `collection.view` / `collection.create` | `collection.transaction.read` / `collection.transaction.record` |
| `ratecard.publish` | `pricing.ratecard.approve` |
| `settlement.finalize` | `settlement.finalize` (identical) |
| `payment.retry` | `payment.retry` (identical) |
| `receipt.download` | `receipt.download` (identical) |
| `user.view` / `user.disable` | `identity.user.read` / `identity.user.manage` |
| `role.view` / `role.create` | `authz.role.read` / `authz.role.manage` |
| `audit.view` | `audit.read` |

The AUDITOR set is additionally checked **structurally** by a test: no key in
it ends in `manage`, `record`, `finalize`, `retry`, `approve`, `write`,
`delete` or `export`. That catches a permission carelessly copied into the
read-only role later.

---

## 9. Centre-level access

`user_role.center_id`, nullable.

* **NULL means organization-wide**, which is what every grant written before
  this migration means — so adding the column narrowed nobody.
* A value restricts **that grant** to one centre. The scope lives on the grant
  rather than the role because the same role is worth granting at different
  scopes: a person can run centre A and later centre B without a second role
  being invented for them.
* A principal is centre-scoped only if **every** grant names a centre. One
  organization-wide grant makes them organization-wide.

This fills the hint the engine reserved from the start
(`TODO(M2): attribute-based conditions (e.g. own-center-only)`). It is
deliberately **not** a general condition language — a centre id is the only
scope this business has, and an engine to express it would be a larger thing to
get wrong.

Enforced in three places: `require_center_access` on the centre-bearing routes;
in the handler where the centre arrives in a request body (opening a session);
and as a `WHERE` clause on the centre and transaction lists, so a scoped user
*sees* only their own.

**The refusal is 403, not 404** — a deliberate departure from the cross-tenant
rule, and the reason is in the source: another organization's centre must not
be shown to exist, but a centre in your own organization is not a secret from
you. Pretending it does not exist would send an operator hunting for a typo
instead of telling them they are not assigned to it.

---

## 10. Backend authorization changes

* `get_current_principal` — membership checked per request.
* `require_center_access(param)` — new guard, audited on refusal.
* `PermissionEngine.center_scope()` — resolves the scope set, or `None`.
* `assign_role(..., center_id=)` — grants can carry a scope; re-granting at a
  different centre **rescopes** the existing row rather than accumulating a
  second silent grant, and records `authz.role.rescoped`.
* `GET /v1/authz/roles` — new.
* `POST /v1/members/{id}/status` — new, audited.
* `GET /v1/members` — carries each member's roles and centre scope, from the
  same rows the engine reads, so the screen and the enforcement cannot disagree.
* `GET /v1/auth/me` — organization, membership, roles (with scope), centre
  scope, permissions. No password hash, no session id, no token; a test asserts
  the serialized response contains none of `password`, `hash`, `token`,
  `secret`, `refresh`.
* Centre and transaction lists filter by scope in SQL.

---

## 11. Frontend authorization changes

* **The Roles page no longer invents roles.** It opened with
  `const SYSTEM_ROLES = ["tenant-admin", "tenant-operator", "tenant-viewer"]` —
  and `tenant-operator` has never existed on this platform, so the page offered
  an administrator a role that could not be granted and the grant failed at the
  API. It now lists the real roles with their permissions, whether they are
  platform or organization-defined, and how many people hold each; and it can
  grant at a centre scope.
* **The Users page** shows role, centre scope **by name**, last sign-in
  ("never" when there has not been one), and offers membership suspension
  distinctly from account deactivation.
* Navigation was already permission-driven and needed no change — which the
  live verification confirms role by role.

Frontend hiding is not treated as a boundary anywhere: every control the portal
shows sends a request the backend checks again, and §13 demonstrates the
refusals with the portal ignored entirely.

---

## 12. Database migrations

| Revision | Change |
|---|---|
| `a3f81c46b204` | `user_role.center_id` (nullable, indexed); `user_account.last_login_at` (nullable). Expand-only, no backfill, no row rewritten. |
| `b7c2e94d1a55` | De-duplicate system roles; add the partial unique index `uq_role_system_name`. |

Both verified up → down → up on a scratch database, and applied by the standard
deployment pipeline. The role/permission seed is idempotent by construction and
now also race-safe.

---

## 13. Existing users migrated

**Additive.** Every existing user KEPT the role they held and gained the named
equivalent, so nothing that worked stopped working.

| User | Held | Gained | Kept |
|---|---|---|---|
| `manager@lacteva-demo.example.com` | `tenant-admin` | `ORGANIZATION_ADMIN` | yes |
| `viewer@lacteva-demo.example.com` | `tenant-viewer` | `AUDITOR` | yes |
| `manager@lacteva-isolation.example.com` | `tenant-admin` | *(unchanged)* | yes |
| platform root users | `platform-admin` | *(unchanged; `PLATFORM_SUPER_ADMIN` is available)* | yes |

`ORGANIZATION_ADMIN` and `tenant-admin` carry identical permission sets, so the
demo manager's access is unchanged to the key. Both grants are organization-wide,
so the centre scope stays `None`.

Seven users were created for the live role demonstration — one per role, which
§17 requires and which cannot be shown otherwise. They use the existing demo
password constant; **no credentials appear in this report**.

---

## 14. Tests added

**Backend — `tests/test_rbac_foundation.py`, 28 tests**, covering all twelve
§15 categories:

| § | Test |
|---|---|
| 1 | unauthenticated on 7 endpoints; a forged token |
| 2 | an organization admin reaches what the role grants |
| 3 | manager cannot finalize/create settlements or define roles; officer cannot finalize or administer users or publish rate cards |
| 4 | cross-organization read is 404 and the list excludes it |
| 5 | centre-scoped user refused another centre (403), refused opening a session there, and sees only their own in the list |
| 6 | organization manager vs finance manager on the same request |
| 7 | auditor reads eight endpoints and is refused six mutations; plus a structural check that no AUDITOR key mutates |
| 8 | collection operator can collect and is refused eight administration surfaces |
| 9 | a suspended member's existing token stops working immediately |
| 10 | the backend refuses a guessed URL, a body naming another centre, and a header claiming another tenant |
| 11–12 | the existing suites, unchanged |

Plus: `/v1/auth/me` carries the context and no secrets; scope reported as null
when organization-wide; last-login recorded; every named role exists after
bootstrap; seeding twice does not duplicate; a role grant is audited; and a
second system role with the same name is refused by the database.

**Portal — `src/app/admin/rbac-pages.test.tsx`, 10 tests, plus 2 on the
dashboard's unauthorized state**: the roles page
lists what the platform has (and not `tenant-operator`), distinguishes platform
from organization roles, shows holders and permissions, grants with and without
a centre scope; the users page shows role and scope by name, last sign-in and
"never", suspends through the platform and offers reinstatement.

---

## 15. Test results

```
backend      1,265 tests — 1,191 passed, 74 skipped (PostgreSQL-only), 0 failed
PostgreSQL      74 tests — 74 passed against a real engine; POSTGRESQL PROOF PASSED
portal         162 tests — 162 passed (13 files)
ruff check + ruff format --check      clean (210 files)
eslint src --max-warnings 0           clean
tsc --noEmit                          clean
npm run build                         clean
validate_docs.py                      170 files, all checks passed
alembic up → down → up                clean, both revisions
```

No existing test was weakened or deleted. Five call sites were updated for the
`/v1/audit` page shape in DEMO-007 and none for DEMO-008; the portal session
fixture gained the new context fields without changing what it asserts.

---

## 16. Live verification

Deployed to **https://dev.phoenixsoft.in** as `demo008-24cbada`, then every
role signed in through a **real browser** and probed at the API with the portal
ignored.

| Role | Perms | Centres visible | Navigation | API refuses |
|---|---|---|---|---|
| ORGANIZATION_ADMIN | 41 | 5 | all 18 | — |
| ORGANIZATION_MANAGER | 18 | 5 | 14 (no Users, Roles, Audit, Configuration) | audit, roles, create supplier, create role |
| CENTRE_MANAGER | 9 | **1** | 6 | payments, receipts, rate cards, audit, members, roles, both writes |
| COLLECTION_OPERATOR | 6 | **1** | 4 (Dashboard, Centres, Suppliers, Transactions) | settlements, payments, receipts, rate cards, audit, members, roles, both writes |
| FINANCE_OFFICER | 11 | 5 | 8 | rate cards, audit, members, roles, both writes |
| FINANCE_MANAGER | 14 | 5 | 8 | rate cards, audit, members, roles, both writes |
| AUDITOR | 18 | 5 | 17 (read-only) | every write |

The distinctions the table cannot show, probed directly:

```
FINANCE_OFFICER vs FINANCE_MANAGER — the same request, different authority
  403  officer  POST /settlements/{open}/finalize
  200  manager  POST /settlements/{open}/finalize

CENTRE SCOPE — same organization, different centre
  200  centre manager GET /collection-centers/{assigned}
  403  centre manager GET /collection-centers/{other}
  403  centre manager GET /collection-centers/{other}/readiness
  403  operator POST /collection-sessions at another centre

AUDITOR
  200  GET  /audit          403  POST /settlements/{id}/finalize    403  POST /collection-sessions

CROSS-TENANT — unchanged from DEMO-003..007
  404  org admin GET /milk-transactions/{foreign}

IMMUTABILITY still holds
  409  finance manager POST /settlements/{finalized}/finalize   (BR-0010)
```

---

## 17. Data changes

| Change | Count |
|---|---|
| Users created (one per role, for §17) | 7 |
| Existing users given an additional named role | 2 |
| System roles de-duplicated | 6 rows merged away |
| Grants lost in the merge | **0** (13 users still hold roles) |
| Settlements finalized | **1, unintended** — see below |
| Records deleted | 0 |
| Reseeds | 0 |

**One unintended change, stated plainly.** The live probe that demonstrates
`FINANCE_OFFICER` cannot finalize and `FINANCE_MANAGER` can pointed both
requests at a *real open settlement*. The officer was refused at the guard; the
manager was permitted, so the domain went ahead and finalized
**STL-2026-000050 (7,280.00 KES)** at 16:21:25 UTC. It is a legitimate business
operation on a legitimately calculated settlement, correctly attributed in the
audit trail to `financemgr@lacteva-demo.example.com` — but it was not intended,
and it consumed one of the two settlements DEMO-007 left open for the live
demonstration. **One open settlement remains** (STL-2026-000051, 4,704.00 KES).
The probe script now targets an id that cannot succeed, so a permission check
can no longer perform the operation it is checking.

---

## 18. Security concerns

1. **Suspension was ineffective** — found and fixed (§4). Anyone suspended
   before this release retained access until their token expired.
2. **Duplicate system roles** — found and fixed (§5). Not exploitable, but the
   database could not enforce a uniqueness the code assumed.
3. **`is_active_member` treats a missing membership row as active.** Deliberate
   and pre-existing: platform principals have no membership, and so do users
   created before memberships were backfilled. It means a tenant user whose
   membership row was never created is not suspendable by that mechanism. The
   original `TODO(M2): backfill memberships and make the row mandatory` still
   stands and is the right next step.
4. **Permission resolution is one query per request, uncached.** Correct and
   immediate — revocation applies to the very next request — but it is a
   per-request database read. The `TODO(M1)` Redis cache would need explicit
   invalidation on every grant change, or it would reintroduce exactly the
   staleness §4 just removed.
5. **No MFA.** Out of scope by §19; the architecture is ready for it (§3).
6. **Organization-scoped custom roles can be created by any holder of
   `authz.role.manage`**, with any registered permission — including
   `settlement.finalize`. An organization administrator can therefore grant
   themselves nothing they did not already have, but *can* construct a role
   that concentrates authority the default roles separate. That is a policy
   question rather than a defect, and worth an explicit decision later.

---

## 19. AWS impact

| | |
|---|---|
| AWS resources created | **0** |
| AWS resources resized | **0** |
| Managed services created | **0** |
| Terraform infrastructure changes | **0** |
| Additional AWS cost | **0** |

PostgreSQL, Redis and RabbitMQ remain in Docker Compose on the existing EC2
instance. Two container images were built on that host and pushed to the ECR
repositories every previous release has used.

---

## 20. Limitations

1. Permission **names** were not changed to the work order's vocabulary; the
   mapping is in §8 and the reason in §6.
2. **Centre scope covers the centre-bearing surfaces**, not every endpoint that
   could theoretically be narrowed. Suppliers, settlements and payments are not
   centre-filtered — a centre manager sees the organization's suppliers. Whether
   they should is a business question the brief does not settle.
3. **No custom-role builder beyond what already existed** (§10 explicitly makes
   it optional). The page can create an organization role from the registry.
4. **Invitations still grant a placeholder role** (`tenant-viewer`) which is
   then swapped. The invitation API takes a role name, so this is avoidable —
   it was not changed because the invitation flow is load-bearing for every
   existing test.
5. **`last_login_at` is not backfilled**; existing accounts read "never" until
   they next sign in. Backfilling from `created_at` would have manufactured a
   login that never happened.
6. The **live role verification runs headless**. Real Chrome against the real
   deployment, but not a human's rendering path.
7. **The dashboard is still the landing page for every role**, including those
   without `reporting.read`. It now says so calmly rather than showing errors
   (§22), but a role-appropriate landing page would be better than a mostly
   empty one.

---

## 22. Found and fixed during live verification

Signing in as each role surfaced something no test had: a **collection
operator's dashboard was a wall of red failure panels**. Their navigation was
correctly restricted to four destinations, and then their landing page reported
that the summary "could not be loaded", the trend was "unavailable", and so on
— because every aggregate on it 403s for a role without `reporting.read`.

Honest about the status code, wrong about the situation. Nothing was broken;
reporting is not part of that job. An operator who believes the platform is
broken raises a support ticket instead of getting on with their work.

The loader now distinguishes *forbidden* from *failed*. A 403 renders as
"Reporting is not part of your access… nothing here is broken"; a genuine 500
still renders as a failure with a retry. Both are tested, and the corrected
screen was confirmed live.

---

## 21. Recommended DEMO-009

**Customer management and the sales side** — the roadmap's next business
priority and what the waiting dairy customers actually asked for:

1. Customer management
2. Daily milk delivery
3. Daily delivery report
4. Monthly customer bill
5. Customer payment
6. Customer receipt

The procurement half of this platform (supplier → collection → settlement →
payment → receipt) is complete and demonstrated. The sales half is the mirror
image, and the modules it needs — pricing, settlement, payment, receipt,
notification, reporting — already exist and are proven. The work is a
`customer` bounded context and a `delivery` one, reusing the financial
machinery rather than duplicating it.

Two things to carry forward from this work order: the new roles will need
customer-side permissions (`customer.read`, `delivery.record`, and a
`SALES_OFFICER` role), and the same rule applies — a permission is only real
once the platform has been made to refuse without it.

---

## Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-08-12 | Platform Engineering | DEMO-008: found that authorization was already database-driven and reported that plainly; fixed a live security defect (a suspended member kept working until their token expired, and their refresh token kept minting new ones) and a data-integrity defect found only by inspecting the deployed system (system roles could be duplicated because a composite unique constraint containing NULL enforces nothing — three copies existed of each); added the eight named roles composed from existing permission keys, centre-scoped grants with 403-not-404 refusal inside an organization, the roles read endpoint the portal had been hard-coding around, membership suspension, and the full authorization context on `/v1/auth/me`; 38 new tests across the twelve §15 categories; every role verified live in a real browser and again with the portal ignored. Deployed as `demo008-24cbada`. |
