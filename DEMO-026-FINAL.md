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

## 12. Known limitations

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

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-026: one subscription table, a plan registry with no invented prices, a 30-day trial counted on the dairy's own clock and anchored to its own creation, and one authoritative entitlement decision. No payment provider, no fake payment states. |
