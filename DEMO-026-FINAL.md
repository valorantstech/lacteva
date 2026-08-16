---
id: DEMO-026-FINAL
title: DEMO-026 — SaaS Subscription, 30-Day Trial & Entitlement
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-025-FINAL, DEMO-024-COMPETITIVE-REVIEW, DEMO-021-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-026 — SaaS Subscription, 30-Day Trial & Entitlement

Lacteva can now tell a dairy what it is entitled to use and until when. It
**cannot take money**, and nothing here pretends otherwise.

---

## 1. What already existed

Nothing commercial. The survey found **no** subscription, plan, trial,
entitlement or payment concept anywhere — the first genuinely greenfield
milestone in a long while.

What it did find, and what this was built on:

| Piece | Where |
|---|---|
| `organization.created_at` — the authoritative onboarding instant | `organization` |
| `organization.timezone` / `currency_code` from the country registry | DEMO-013 |
| `collection_center.status` with `active` | DEMO-005 |
| Business-date conversion on the organization's own clock | `core/business_time.py` |
| A tenant configuration store | `config_entry` |
| A permission registry, and `platform-admin` holding the wildcard | `authz` |
| RLS derived from model metadata | `core/rls.py` |

## 2. What DEMO-026 added

**One table, one registry, one service.**

* `subscription` — tenant-owned, `tenant_id` **UNIQUE**, holding the plan, the
  status, the trial dates and the payment-provider fields nobody writes yet.
* `plans.py` — the plan catalog as a **registry, not a table**. A plan is a
  decision the product makes, not data a tenant owns; a table would have been
  platform-global and would have needed an RLS exemption to explain.
* `SubscriptionService` — trial creation, status derivation, entitlement, the
  centre guard, and the operator-only activation path.

Plus: two hooks (trial at organization creation, entitlement at centre
activation), four endpoints, two permissions, and a small read-only portal page.

## 3. Subscription model

```
Organization ──1:1── Subscription ──▶ Plan (registry) ──▶ Entitlement
```

**Statuses: `trialing`, `active`, `cancelled`, `expired`.**

`past_due` was considered and **deliberately not implemented**. It means "a
payment attempt failed", and nothing in this platform can know that — there is
no payment provider. A `past_due` column would be a state Lacteva could set and
never verify, which is exactly the fake payment state the work order forbids.
It arrives with the provider that can report it.

## 4. Trial model

**30 days, counted on the dairy's own calendar, anchored to its own creation.**

`trial_started_on = business_date_of(organization.created_at, organization.timezone)`
and `trial_ends_on = trial_started_on + 30 days`. Both are **stored**, so the
window cannot drift if the organization's timezone is later corrected — the
trial a dairy was given is a fact about what it was given.

Status is *derived* from those dates against the organization's business date
today. Day 0 through day 29 are `trialing`; day 30 is `expired`.

**The trial cannot restart.** `ensure_trial` is get-or-create, so logging in
again, a user joining, a centre being created, a worker retrying and the
platform restarting all find the existing row. Proven by test, and by a
mutation: deleting the Python existence check changes nothing, because the
**unique constraint** is the guarantee and the read is only an optimisation.

**No data migration.** Organizations that predate this milestone acquire their
trial lazily on first read, counted from their own `created_at` on their own
clock. Backfilling in SQL would have had to pick a date without a clock and
would have been wrong for every tenant not on UTC.

## 5. Plan model

| | `LACTEVA_TRIAL` | `LACTEVA_STANDARD` |
|---|---|---|
| Billable | no | yes |
| Included centres | **unlimited** | 0 — it covers what it subscribes for |
| Capabilities | everything | everything |

**No price appears in source.** The commercial decision made so far is the
*shape* — 30-day trial, per collection centre, not per user, not per litre. The
actual INR/KES/QAR numbers are a question nobody has answered, so putting one
in Python would be inventing a fact. A deployment that has decided sets
`subscription.price.LACTEVA_STANDARD.INR` in the existing configuration store,
and the API reports `price: null` until somebody does.

The trial is unlimited on centres deliberately: everything is available while a
dairy evaluates, and meeting a wall you were never asked to pay past is how an
evaluation ends badly.

## 6. Entitlement architecture

    PERMISSION   — who may do this?                    authz, unchanged
    ENTITLEMENT  — may this organization do it at all?  SubscriptionService

One authoritative decision, in one place. No module asks "is the trial still
running?" — they ask this service or they ask nothing. Mixing the two produces
the failure where a dairy's own administrator is told they lack permission when
what actually happened is that a trial ended: different message, different
remedy.

`can_read` is modelled and is **always true**. An expired dairy keeps every
collection, settlement, invoice and receipt it has and keeps being able to read
them. Taking a dairy's own records away for a commercial reason would be a
worse product than not selling one.

## 7. Centre-based pricing foundation

`active_centres` counts centres in `active` status — not users, not litres. A
centre in maintenance or archived is not doing work and is not billed for.

**The one place a commercial limit touches operations is centre activation**,
and it guards *activation* rather than creation: a dairy may always record the
centres it has; what it may not do is put more of them to work than it pays
for. Centres already active are **never** deactivated by a limit — a subscription
covering fewer centres than are running shows an overage and changes nothing
else.

Nothing is refused during a trial.

## 8. Onboarding relationship

The backend supports the intended flow end to end: sign up → create
organization (country → currency, timezone, language from the registry) →
**trial starts here** → create centres → operate. The trial is created eagerly
at organization creation and lazily on first read, so no onboarding path can
produce an organization without one. No onboarding UI was built or changed.

## 9. Payment-provider readiness

`payment_provider`, `external_customer_id`, `external_subscription_id` and
`external_price_id` exist, are nullable, are **never written**, and are
deliberately opaque strings — the business domain must not learn the shape of
any one vendor's identifiers. There is no gateway, no credential and no
checkout. **Customers cannot pay.**

## 10. Notification integration

**None, deliberately.** DEMO-025's providers are all `disabled` on this
deployment, so a `TRIAL_EXPIRING` event would produce a message nobody
receives. The events are worth emitting when a channel is live; emitting them
now would add a moving part whose only observable effect is a `disabled`
refusal in the notification history.

## 11. Security and RLS

`subscription` is tenant-owned, so `core/rls.py` derives it into the protected
set from the model metadata and the migration installs the policy through the
same machinery every other tenant table uses. **66 tables enabled and forced.**

The service is constructed from the **authenticated principal's** tenant, never
from a path, body or header — there is no request in which a caller can ask
about another organization's commercial standing.

**A client cannot forge a status.** There is no endpoint that accepts one; a
test walks the OpenAPI schema and fails if any subscription request body ever
grows a `status` field. Reading is a tenant-administrator permission; changing
is behind `organization.subscription.manage`, which **no tenant role holds** —
only `platform-admin`, via its wildcard. Until a payment provider exists, the
only truthful way to become `active` is for somebody at Lacteva to say so.

## 12. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — the nine-step proof, on real PostgreSQL from
the `pgserver` wheel, no Docker and no root. **PASSED.**

    1/9   migrations apply to an EMPTY database — head is c7e4a2f19b83
    1b/9  migrations back-fill EXISTING rows
    2/9   RLS enabled AND forced on every tenant-owned table — 66 policies
    3/9   PostgreSQL-only suites — 104 passed, 0 skipped
    4/9   a real dairy seeded through the platform's own API
    5/9   logical backup + checksum verification
    6/9   a SECOND, fresh database migrated
    7/9   restore into it
    8/9   deep integrity of the restored database
    9/9   source and restored compared fact by fact

`tests/test_subscription_concurrency_postgres.py` is in the proof's explicit
file list — a suite that is not listed is a suite that never runs — and all
five of its tests executed:

* **eight concurrent signups produce one trial**, and every caller receives the
  *same* window. A dairy that double-clicks must not get sixty days, and a race
  that returned different dates to different callers would be a trial nobody
  could reason about.
* a second call much later does not extend it.
* a subscription **neither leaks nor deletes across tenants** — the probe runs
  SQL with no tenant filter at all, so the database itself must refuse.
* the table has `relrowsecurity` **and** `relforcerowsecurity`.
* `uq_subscription_tenant` exists, named explicitly, because it — not Python —
  is what stops a second trial.

This half cannot be proven on SQLite: the test stack shares a single connection
and true concurrency never happens.

## 13. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **1722 passed**, exit 0 |
| `tests/test_subscription.py` (new) | 24 |
| `tests/test_subscription_concurrency_postgres.py` (new) | 5, on real PostgreSQL |
| `ruff check` + `ruff format --check` | clean, 278 files |
| Admin portal (`vitest`) | **256 passed** (19 files) |
| Portal `tsc --noEmit`, `eslint --max-warnings 0`, `next build` | clean |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |
| `validate_docs.py` / `generate_xref.py` | 196 files, 66 IDs — passed |

**Two defects were found by the gates, not by reading:**

1. **`test_every_tenant_owned_table_is_covered_by_a_policy` failed on
   `subscription`.** The migration installed the policy correctly and from a
   snapshotted list — what was missing was the declaration in the build check's
   union, which is hand-written precisely so that a new tenant-owned table
   cannot become protected *by accident*. The check refused until the table was
   named. That is the guard working, and it is why the union is not generated.
2. **The portal's "ended N day(s) ago" hint could never render.** It was gated
   on `status === "trialing"`, but a trial that has ended reports `"expired"` —
   so the date disappeared at exactly the moment an administrator needs it. The
   test was right and the page was wrong; the page was fixed.

The guards were mutation-checked rather than merely exercised: deleting the
`ensure_trial` existence check leaves every test green (correctly — the unique
constraint is the guarantee), while removing the activation guard, the
permission, or the resolver's answer fails the suite.

## 14. Production verification

Deployed `main-79d0738` to **https://dev.phoenixsoft.in** through the existing
path — git → GitHub Actions → ECR → `deploy.sh` (pull → backup → migrate →
deploy → verify → smoke). No flags, no forcing, no manual schema edits.

    schema at c7e4a2f19b83 (matches the image)
    database, redis, outbox, consumers, projections,
    notifications, jwt_keys, background_workers — all healthy
    every tenant-owned table has a policy; policies are FORCED
    the API role lacteva_app is NOSUPERUSER/NOBYPASSRLS
    DEPLOYMENT VERIFIED — the platform is serving
    SMOKE TEST PASSED

**Trials materialized on production, on each dairy's own clock** (REAL — these
are the live tenants, reading through the live API):

| Organization | Country | Currency | Trial started | Trial ends | Days left | Active centres | Price |
|---|---|---|---|---|---|---|---|
| Lacteva India Demo | IN | INR | 2026-08-14 | 2026-09-13 | 28 | 3 | `null` |
| Lacteva Demo Cooperative | KE | KES | 2026-08-12 | 2026-09-11 | 26 | 5 | `null` |

Both derive exactly as predicted from `organization.created_at` on
`Asia/Kolkata` and `Africa/Nairobi`. Reading three times in a row returned the
same window each time, and the table holds **exactly two rows** — one per
organization that has been read — because creation is lazy and idempotent. The
payment columns are NULL, as they will remain until a provider exists.

**The guards refuse in production:**

| Attempt | Result |
|---|---|
| No token | **401** |
| Tenant admin activates a paid plan | **403** (rendered in Hindi — the tenant's own locale) |
| Tenant admin cancels | **403** |
| Client supplies `?status=active` | ignored — still `trialing` |

`GET /admin/subscription` serves 200 in the portal. **The browser walkthrough
was NOT performed**: the Chrome extension is not connected in this session, so
the page was verified by its route, its rendered content and its own test
suite, not visually. That is a gap, and it is stated rather than papered over.

## 15. Financial safety

A verified backup was taken **before** deploying — 65 tables, 41,475 rows,
26.6 MB, `verified: true`, plus a second explicit verify pass — and `deploy.sh`
took its own pre-flight backup on top of that.

Every financial figure is **identical** across the deployment:

| | Before | After |
|---|---|---|
| Invoiced | 809038.00 | **809038.00** |
| Receivables | 809038.00 | **809038.00** |
| Received | 444105.00 | **444105.00** |
| Settled (net) | 353417.50 | **353417.50** |
| Collections | 534 | **534** |
| Settlements | 84 | **84** |
| Invoices / receipts / payments | 31 / 24 / 42 | **31 / 24 / 42** |
| Organizations / active centres | 5 / 10 | **5 / 10** |

The only count that moved is users, 103 → 104: the deployment's own smoke test
registers a throwaway account and deletes nothing, by design.

No historical record was modified, no migration touched existing rows — the
migration is pure DDL — and no data was deleted. All ten active centres stayed
active: every organization is on the trial plan, which is unlimited on centres,
so the new guard refused nothing that was already running.

## 16. Known limitations

* **No payment.** Stated once more because it is the thing most likely to be
  misremembered.
* **`past_due` does not exist**, by design (§3).
* **Only centre activation is entitlement-guarded.** Collections, deliveries,
  invoices and settlements are not, and I did not add restrictions the work
  order did not justify. `can_operate` is exposed for whoever wants more.
* **No renewal, dunning, proration or invoicing of the subscription itself.**
  `current_period_end` is a date somebody sets; nothing advances it.
* **Cancellation is immediate** and has no end-of-period grace.
* **Prices are unset.** Every deployment reports `price: null` until configured.
* **No usage metering.** Centre count is computed on demand, not sampled over
  time, so a per-centre bill for a month in which centres changed would need
  a metering decision nobody has made.

## 17. Exact commercial capabilities now supported

**REAL — running on production right now**

* Every organization has exactly one subscription, created idempotently and
  proven idempotent under real concurrency.
* A 30-day trial counted on the organization's own calendar from its own
  authoritative creation instant, and it cannot restart — not when a user
  joins, not when a centre is created, not on logout, not on restart.
* One authoritative, server-derived entitlement: status, days remaining,
  whether the organization may operate, whether it may read, active centres,
  allowance, and whether it is within it.
* A commercial limit on **collection-centre activation** — centre-based, never
  per user and never per litre — that refuses beyond a paid allowance, never
  refuses during a trial, and never deactivates a running centre.
* Graceful expiration: data intact, users intact, administrators not locked
  out, records readable.
* Multi-country by construction — India and Kenya differ by currency and
  timezone from the country registry, and **no country appears anywhere in the
  subscription source**, asserted by a test.
* Server-authoritative status, with no endpoint that accepts one.
* A read-only portal page and two permissions, one of which no tenant role
  holds.

**TEST / DEMO only**

* The production tenants are demo dairies. Their trials are real trials on real
  rows; the dairies are not paying customers.
* `LACTEVA_STANDARD` has never been activated on production. Activation is
  covered by tests and by an operator-only endpoint that returned 403 to a
  tenant administrator when tried live.
* The concurrency proof's eight racing signups are fabricated tenants, cleaned
  up after each test.

**NOT IMPLEMENTED**

* **No payment provider, no credential, no checkout — customers cannot pay.**
  The `payment_provider` / `external_*` columns exist, are nullable and have
  never been written.
* No `past_due`, by design — nothing can verify it.
* No prices. Every deployment reports `price: null` until one is configured.
* No renewal, dunning, proration, subscription invoicing, or usage metering.
* No trial-expiry notifications (every channel is `disabled` on this
  deployment, so they would reach nobody).
* No self-service signup, plan-change or upgrade UI.
* No entitlement guard on collections, deliveries, invoices or settlements —
  only on centre activation.

## 18. Recommended DEMO-027

The honest next question is not "add Stripe" — it is **which of the two gaps
above is actually blocking a sale**, and the answer is probably neither yet.

**Recommended: Commercial Foundation III — trial lifecycle communication and
the operator's console.** A trial that nobody is told is ending is a trial that
expires by surprise, and today the only way to see a tenant's commercial
standing is to be that tenant. Concretely: `subscription.trial_expiring` and
`subscription.expired` events through the existing outbox and relay, with
templates in all four languages, wired to whichever channel a tenant chose —
and a platform-admin view listing every organization's plan, status, trial end
and active centres, which is the screen Lacteva itself needs before it can sell
anything. This needs no vendor, no credential and no commercial decision, and
it is the work that makes the milestone after it possible.

**Then: the payment provider**, once the prices exist. That milestone is
blocked on a business decision, not on engineering — the columns, the boundary
and the `past_due` state are all deliberately shaped to receive it, and doing
it before a price is agreed would mean inventing the thing this milestone
carefully refused to invent.

**Not recommended yet:** usage metering and per-centre proration. They are only
meaningful once a bill exists to be prorated.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-026: one subscription table, a plan registry with no invented prices, a 30-day trial counted on the dairy's own clock and anchored to its own creation, and one authoritative entitlement decision. No payment provider, no fake payment states. |
