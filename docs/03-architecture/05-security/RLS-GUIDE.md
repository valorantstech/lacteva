---
id: RLS-GUIDE
title: Row Level Security Guide
type: reference
status: Approved
version: "1.1"
owner: Architecture Board
created: 2026-08-05
last-updated: 2026-08-06
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
        → SET LOCAL lacteva.tenant_id = '<uuid>'      ← transaction-scoped
        → every query is filtered by the policy, whatever the SQL says
```

`SET LOCAL` matters more than it looks: it is scoped to the transaction, so a **pooled connection cannot carry one request's tenant into the next request's query**. A `SET` without `LOCAL` would be a cross-tenant leak with extra steps.

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

## 4. The bypass

Some machinery is definitionally cross-tenant: the relay dispatcher, event consumers, projection rebuilds, and platform-admin operations. They call `bind_platform_context(session, reason=...)`, which sets `lacteva.bypass_rls` for that transaction and logs the reason.

This is deliberately an **explicit, auditable, transaction-scoped** escape hatch rather than a second superuser connection. Every place the guarantee is stepped around is greppable and logged.

## 5. Testing strategy — and its honest gap

| Environment | Database | What is proven |
| --- | --- | --- |
| Unit / integration suite | SQLite in-memory | Application-level isolation; policy DDL shape; **coverage** of every tenant-owned table |
| `row-level-security` CI job | PostgreSQL 16 | The policies actually execute: reads, updates, deletes, and cross-tenant writes all refused |

**SQLite has no row-level security.** `bind_tenant` is a no-op there, and a test asserts that explicitly so the suite cannot quietly believe it is protected. This is a real divergence between test and production, and it is the reason the PostgreSQL job exists and why a *skip* in that job fails the build.

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
| 1.1 | 2026-08-06 | Architecture Board | CI-001: platform-global (`tenant_id IS NULL`) clause added to the policy after first execution on a real engine. |
| 1.0 | 2026-08-05 | Architecture Board | Established by SEC-001. |
