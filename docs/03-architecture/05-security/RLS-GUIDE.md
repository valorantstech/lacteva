---
id: RLS-GUIDE
title: Row Level Security Guide
type: reference
status: Approved
version: "1.4"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-07
related: [SECURITY, SECURITY-CHECKLIST]
baseline: ARCH-BASELINE-V1
---

# Row Level Security Guide

How PostgreSQL became authoritative for tenant isolation, and what that means for anyone writing a query. Established by SEC-001.

## 1. Why

Before SEC-001, isolation held because every query remembered `WHERE tenant_id = :tenant`. That is a discipline, and disciplines fail **silently**: one forgotten predicate in one new module leaks another dairy's milk, and no test necessarily catches it because the query returns plausible data.

RLS inverts the failure mode. A query that forgets its filter now returns **nothing** instead of everything.

Application filters stay exactly where they are. They are still correct, still needed for sane query plans, and now serve as defense in depth rather than the sole defense.

## 2. How a request reaches its rows

```
request → tenant established (token claim, or X-Tenant-ID hint)
        → SELECT set_config('lacteva.tenant_id', '<uuid>', true)   ← transaction-scoped
        → every query is filtered by the policy, whatever the SQL says
```

The transaction scope matters more than it looks: the setting dies with the transaction, so a **pooled connection cannot carry one request's tenant into the next request's query**. A session-scoped setting would be a cross-tenant leak with extra steps.

**Why `set_config(...)` and not `SET LOCAL ... = :tenant`.** `SET` is *utility syntax*, not a query: PostgreSQL will not accept a bind parameter in it, and asyncpg sends every statement as a prepared statement. `SET LOCAL lacteva.tenant_id = $1` is therefore a **syntax error** — and since the binding runs in `get_session`, before any handler, it was raised on every single request. The platform could not serve one request on its production engine.

That code was written in SEC-001 and first executed in VER-001, because SQLite makes `is_postgres()` false and the function returned before reaching the statement. `set_config(name, value, is_local)` is an ordinary function, so it takes parameters, and `is_local => true` gives exactly `SET LOCAL` semantics. Interpolating the tenant into the SQL string would also have "worked", and would have put a request-controlled value into a statement — the wrong fix.

Authentication re-binds after the token is verified, because the header-derived tenant is only a starting point and the token's claim is authoritative.

## 3. The policy

Each tenant-owned table gets one policy covering all four operations:

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE  ROW LEVEL SECURITY;
CREATE POLICY <t>_tenant_isolation ON <t>
  USING      (current_setting('lacteva.bypass_rls', true) = 'on'
              OR tenant_id IS NULL
              OR tenant_id::text = current_setting('lacteva.tenant_id', true))
  WITH CHECK (current_setting('lacteva.bypass_rls', true) = 'on'
              OR tenant_id IS NULL
              OR tenant_id::text = current_setting('lacteva.tenant_id', true));
```

Three details carry the whole guarantee:

- **FORCE.** Without it the table *owner* — which is who the application connects as — bypasses its own policies. A policy that exists but is not forced protects nothing here.
- **WITH CHECK, not just USING.** `USING` decides what you can see and modify. `WITH CHECK` decides what you can write. Without it, a caller could **move a row into another tenant**; the insert would succeed and merely be invisible afterwards.
- **`current_setting(..., true)`.** The `true` means "missing is NULL, not an error". An unbound session therefore matches nothing and fails **closed**.
- **`OR tenant_id IS NULL`.** Some rows belong to no tenant by design: a user account before it joins an organization, the role catalog, the outbox log. `NULL = 'anything'` is NULL — neither true nor false — so without this clause those rows are invisible to *every* session and cannot be inserted at all. The original SEC-001 policy omitted it, and nothing caught that until the policies were executed on a real engine (CI-001): **registration itself would have failed in production**. Added by migration `c94b1ea27f31`. The clause is safe because a NULL `tenant_id` is not a wildcard — it means the row is platform-global, and no tenant-owned row is ever written with one.

## 3b. Every table declares an isolation strategy (SEC-002)

SEC-001 built the policy set from a mechanical rule — *does the table have a
`tenant_id` column?* — which produced an incomplete answer, because the schema
had already decided that child rows of a tenant-owned aggregate do not repeat
`tenant_id`. Nineteen tables fell outside the boundary that way. Nobody decided
that `supplier_profile` (names, phones, national IDs) or `settlement_line`
(per-delivery money) should be unprotected; they inherited a rule about columns.

The rule is now a declaration, and there are exactly three answers:

| Class | Meaning | Where it lives |
| --- | --- | --- |
| **A — tenant-owned** | Carries `tenant_id`; the standard policy applies | Derived from the metadata by `tenant_tables()` |
| **B — platform-global** | Deliberately unprotected, **with the reason on record** | `PLATFORM_GLOBAL` in `core/rls.py` |
| **C — mixed** | Holds both tenant and platform rows, or is isolated by a column other than `tenant_id` | `MIXED` in `core/rls.py` |

Category A is *derived* rather than listed, because a hand-kept list is how a
new module ships unprotected. B and C are *declared*, because "this table is
deliberately not protected" is a decision and belongs somewhere the next
reviewer will look. `unclassified_tables()` returns everything in neither
group, and a test asserts it is empty — which is what turns "every table has an
explicit isolation strategy" from a principle into a build failure.

### The five platform-global tables

`consumer_cursor`, `projection_state`, `backup_run`, `event_delivery`, and
`password_reset_token`. The first four are per-consumer, per-projection, or
per-platform bookkeeping with no tenant to speak of. `event_delivery` is
deliberately kept tenant-free so outbox partitions can be detached and dropped
without a dependent policy.

`password_reset_token` is the interesting one, and the reason it is category B
rather than A: **the flow that reads it is definitionally unauthenticated.** A
caller presents a token hash and has no tenant bound — discovering which tenant
the user belongs to is the *point* of the lookup. A policy there would make
password reset impossible for every tenant-scoped user. The rows hold a hash
and an expiry, never a credential, and are unreachable without the plaintext
token.

### `organization` is isolated by identity

`organization` has no `tenant_id` because it **is** the tenant —
`organization.id` is what every other `tenant_id` points at. Before SEC-002 it
had no policy at all, so any bound session could read every row: a tenant could
enumerate the platform's entire customer list. Its policy compares its own
primary key instead:

```sql
CREATE POLICY organization_tenant_isolation ON organization
  USING      (current_setting('lacteva.bypass_rls', true) = 'on'
              OR id::text = current_setting('lacteva.tenant_id', true))
  WITH CHECK (... same ...);
```

Note what is **absent**: there is no `OR id IS NULL` escape, and there must not
be. `id` is NOT NULL, so an unbound session sees no organization at all. That
is correct — creating an organization and reading one as a platform
administrator are genuinely cross-tenant acts, and they take the audited bypass
rather than a permanent hole in the policy.

## 3c. Flows that are pre-tenant by nature

RLS assumes a bound tenant. Several legitimate flows run *before* one can
exist, and every one of them was broken by the policy set until SEC-002 —
silently, because SQLite cannot execute a policy.

| Flow | Why it has no tenant yet | Resolution |
| --- | --- | --- |
| **Authenticated request** | `auth_session` and `user_account` are themselves tenant-owned, and the tenant is inside the token that has not been checked against them yet | Bind from the **token's** tenant claim before the first read. The token is signed and self-contained, so its claim is authoritative before any row is read. |
| **Tenant-scoped login** | The tenant is named in the request *body*, which the middleware never sees | Bind from the request before the lookup. This grants nothing on its own — the password still has to verify. |
| **Invitation acceptance** | Anonymous caller; `invitation` is tenant-owned and discovering its tenant is the point | The narrowest possible bypass — one indexed read by token hash — then bind immediately to the tenant it reveals. |
| **Organization creation** | The organization does not exist, so nobody can be bound to it; the slug-uniqueness check must see every tenant's slug | Audited bypass. |
| **Platform-admin reads an organization** | A platform principal has no tenant bound | Audited bypass, after the route's permission guard. A tenant token always binds a tenant, so a tenant caller never reaches that branch. |
| **Self-registration** | The user belongs nowhere yet | `tenant_id IS NULL`, globally visible by design (the CI-001 fix). |
| **Password reset** | Unauthenticated by definition | `password_reset_token` is category B — no policy. |

**The pattern worth naming:** authentication is a chicken-and-egg problem under
RLS. You must read a tenant-owned row to learn which tenant you are, and you
must know which tenant you are to read it. The resolution is always the same —
find the authoritative, *cryptographically or structurally* trustworthy source
of the tenant (a signed token claim, a request parameter that grants nothing on
its own, a single bypassed lookup by an unguessable token) and bind from that
before touching anything else.

**Never pair `set_current_tenant()` with nothing.** It moves the context
variable and leaves the database binding behind, which is a defect that
presents as "the row is invisible to the request that owns it". `rebind_tenant()`
exists to move both together.

## 3d. The bypass boundary (MT-001)

RLS protects the request path. It deliberately does **not** protect the work that spans tenants — the relay dispatcher, the consumer runner, projection rebuilds, the backup engine, the health probes, and the operator APIs that report on all of them. Every one of those is *supposed* to see every tenant.

**For a year that was documented and not implemented.** Those components built sessions from the ordinary factory, which binds neither a tenant nor a bypass. On PostgreSQL the policy then evaluated:

| Clause | Value on an unbound session |
| --- | --- |
| `current_setting('lacteva.bypass_rls', true) = 'on'` | `NULL = 'on'` → not true |
| `tenant_id IS NULL` | true only for platform-global rows |
| `tenant_id::text = current_setting('lacteva.tenant_id', true)` | `uuid::text = NULL` → NULL → not true |

So the entire asynchronous half of the platform could see only platform-global rows: **the relay would find no tenant events to dispatch, consumers would consume nothing, and every projection write would be refused by `WITH CHECK`.** No error, no exception, no alert — requests would succeed, milk would be recorded, and nothing downstream would happen. That is the failure shape this platform's own runbook calls the most dangerous it has.

SQLite cannot execute a policy, so nothing caught it. It is the fourth defect of that exact shape.

### How the boundary is drawn now

Two session factories, and the difference is visible at the construction site:

| Factory | Given to | Sees |
| --- | --- | --- |
| `get_session_factory()` | Everything request-scoped | One tenant (RLS) |
| `platform_factory(reason)` | Relay, consumers, projections, backup, health probes, ops APIs | Every tenant, and says why |

`PlatformSessionFactory` binds `lacteva.bypass_rls` on every session it produces and logs the reason. A component built with it **cannot forget**; a component built with the ordinary factory is visibly request-scoped. That is why it is a factory rather than a call at each of ~25 sites.

### The consequence that matters

**Inside a bypassed session, the application-level `tenant_id` filter is the only isolation there is.** RLS is not a second line of defence there — it is switched off, on purpose. MT-001 found one query that had relied on it: the notification dispatcher looked up a recipient by `subject_id` alone, so a match across the boundary would have addressed one dairy's payment notification with another dairy's phone number.

The rule for anything running under `platform_factory`:

> **Every query filters by tenant explicitly, even where a UUID makes a collision implausible.** The database is not going to catch it, and the cost of the clause is one line.

## 4. The bypass

Some machinery is definitionally cross-tenant: the relay dispatcher, event consumers, projection rebuilds, and platform-admin operations. They call `bind_platform_context(session, reason=...)`, which sets `lacteva.bypass_rls` for that transaction and logs the reason.

This is deliberately an **explicit, auditable, transaction-scoped** escape hatch rather than a second superuser connection. Every place the guarantee is stepped around is greppable and logged.

## 5. Testing strategy — and its honest gap

| Environment | Database | What is proven |
| --- | --- | --- |
| Unit / integration suite | SQLite in-memory | Application-level isolation; policy DDL shape; **coverage** of every tenant-owned table |
| `row-level-security` CI job | PostgreSQL 16 | The policies actually execute: reads, updates, deletes, and cross-tenant writes all refused |

**SQLite has no row-level security.** `bind_tenant` is a no-op there, and a test asserts that explicitly so the suite cannot quietly believe it is protected. This is a real divergence between test and production, and it is the reason the PostgreSQL job exists and why a *skip* in that job fails the build.

### The two ways this suite proved nothing (VER-001)

Both were found by running it, and neither was findable by reading it.

**The tests re-implemented the binding they were testing.** Every case issued its own `SET LOCAL ...` rather than calling `bind_tenant`, so the production binding could raise a syntax error on every request while its own protection suite stayed green. The tests now call `bind_tenant` and `bind_platform_context` directly — a test that builds its own copy of the thing under test is testing the copy.

**The suite ran as a superuser.** A PostgreSQL superuser, and any role with `BYPASSRLS`, **ignores row-level security entirely**. `FORCE ROW LEVEL SECURITY` does not help: `FORCE` closes the loophole for the table *owner*, and says nothing about superusers. The proof pipeline connected as the role the official `postgres` image creates, which is a superuser — so every isolation assertion passed while the database was enforcing nothing at all.

Three things close it:

- The pipeline creates an unprivileged `lacteva_app` role and runs every isolation test as it, asserting first that it holds neither `rolsuper` nor `rolbypassrls`.
- Production connects as that role too (`DEPLOYMENT.md` §2b), and the platform **refuses to start** in `prod`/`staging` if it does not (`assert_rls_is_enforceable`).
- A test asserts the refusal, and another asserts the pipeline's own role is unprivileged — so this cannot regress into a green run again.

The general lesson is worth more than the two fixes: **a proof must establish that the guard is capable of refusing, not merely that it is present.** Checking `pg_policies` for rows was never evidence of enforcement.

The coverage test is the drift guard: it compares the live metadata against the migration's snapshot, so a new tenant-owned table cannot ship without a policy. It has already earned its keep — it caught three projection tables that register at consumer discovery rather than at import.

## 6. Adding a tenant-owned table

1. Add the model with a `tenant_id` column.
2. Write a migration extending the policy set (copy the DDL above).
3. Run the suite — the coverage test fails until step 2 is done.

## 7. Operating

**Verify policies are live:**

```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class WHERE relrowsecurity ORDER BY relname;
```

Both flags must be true. `relrowsecurity` alone means the owner still bypasses.

**Disable safely (rollback):** `alembic downgrade` one revision removes the policies cleanly, or set `LACTEVA_RLS_ENABLED=false` to stop binding without touching the schema. Application filters continue to isolate either way — which is exactly why keeping them was the right call.

**Diagnosing "no rows":** almost always an unbound session. Check that the request authenticated, and that the operation is not platform machinery that should have called `bind_platform_context`.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.4 | 2026-08-07 | Architecture Board | VER-001: `set_config` replaces `SET LOCAL ... = :param`, which was a syntax error on every request; the application role is now a non-superuser, without which every policy was inert; the suite calls the production binding instead of re-implementing it. |
| 1.3 | 2026-08-06 | Architecture Board | MT-001: the bypass boundary documented and implemented — background components were never actually setting the bypass, so the asynchronous half of the platform saw only platform-global rows. |
| 1.2 | 2026-08-06 | Architecture Board | SEC-002: A/B/C isolation taxonomy; 13 child tables made tenant-owned; `organization` isolated by identity; the pre-tenant flows documented. |
| 1.1 | 2026-08-06 | Architecture Board | CI-001: platform-global (`tenant_id IS NULL`) clause added to the policy after first execution on a real engine. |
| 1.0 | 2026-08-05 | Architecture Board | Established by SEC-001. |
