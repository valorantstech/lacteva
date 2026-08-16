---
id: DEMO-027-FINAL
title: DEMO-027 — Commercial Foundation II: Subscription Payment & Activation
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-026-FINAL, DEMO-025-FINAL, DEMO-024-COMPETITIVE-REVIEW]
baseline: ARCH-BASELINE-V1
---

# DEMO-027 — Commercial Foundation II: Subscription Payment & Activation

Lacteva can now take a subscription from trial to active **through a payment
provider it verifies**. It still cannot take money, because no provider has
been contracted — and everything below is careful about the difference.

---

## 1. What DEMO-026 already provided

The survey found the foundation intact and needing no rewrite:

| Piece | State |
|---|---|
| `subscription`, one row per tenant, `tenant_id` UNIQUE | kept |
| `trialing / active / cancelled / expired` | extended, not replaced |
| `plans.py` as a **registry, not a table** | kept |
| `SubscriptionService` — the single entitlement decision | kept |
| 30-day trial on the organization's own clock | untouched |
| `payment_provider`, `external_customer_id`, `external_subscription_id`, `external_price_id` | **now written** |
| `subscription.price.<PLAN>.<CURRENCY>` in the config store | now the per-centre price |
| `organization.subscription.read` / `.manage` | joined by `.pay` |

Two findings shaped everything that follows.

**`modules/payment/` is not this, and must not be extended.** It is PAY-001,
the operational engine paying farmers against finalized settlements, and its
own docstring declares the scope wall: no gateway client, no bank integration,
no provider SDK, no credential handling. A dairy's money and Lacteva's money
share a word and nothing else.

**The provider boundary already had a house shape** in
`modules/notification/providers.py` — a Protocol, a registry, one `_build`
mapping configuration to an adapter, and startup validation that fails the
deployment once rather than each call at runtime. DEMO-027 copies it exactly. A
second shape for the same idea is how two boundaries drift apart.

## 2. What DEMO-027 added

* `providers.py` — the payment boundary: `PaymentProvider`, the four DTOs the
  domain speaks in, a registry, and two adapters (`Disabled`, `Test`).
* `billing.py` — quoting, checkout, server-side verification, applying an
  outcome, activation, grace.
* `webhooks.py` — the only unauthenticated write path in the platform.
* `subscription_payment` and `subscription_payment_event` tables, plus
  `subscription.grace_ends_on`.
* `past_due` as a real status, reachable only from a verified provider signal.
* Four endpoints, one unauthenticated webhook endpoint, one permission.
* A checkout, a payment history and a past-due explanation on the existing
  portal page. No redesign.

## 3. Payment architecture

```
   Organization ──▶ Subscription ──▶ Entitlement      (DEMO-026, unchanged)
                         ▲
                         │ activation
                    SubscriptionBillingService
                         │
                    SubscriptionPayment ──▶ PaymentProvider ──▶ external gateway
                         ▲                        │
                         └── webhook ◀────────────┘
                              (verified, de-duplicated)
```

Three rules govern the whole of it.

**The server owns the amount.** A client sends a plan code and a number of
collection centres. It never sends a price, a total, a currency or a status —
a browser that could name the amount could name one rupee. A test walks the
OpenAPI schema and fails if any subscription request body ever grows one of
those fields.

**The provider owns the confirmation.** Nothing activates a subscription except
an outcome the provider itself reported. A signature proves who sent a message;
it does not prove what is true, so the amount is compared against the stored
intent and a mismatch is refused and recorded.

**A repeat is not a second event.** One open payment per organization, one
payment per provider reference, one action per provider event id — all three
enforced by unique constraints, not by `SELECT`-then-act.

## 4. Provider abstraction

```python
class PaymentProvider(Protocol):
    name: str
    def create_checkout(self, request: CheckoutRequest) -> CheckoutSession: ...
    def verify(self, provider_reference: str) -> PaymentOutcome: ...
    def parse_webhook(self, *, body, headers) -> WebhookEvent: ...
```

Four methods, and **no vendor in any name**. `PaymentOutcome.state` is the
platform's vocabulary (`pending` / `succeeded` / `failed` / `cancelled`), so an
adapter translates `captured` / `paid` / `settled` / `COMPLETE` and the domain
never grows a table of vendor synonyms.

Selection is configuration: `LACTEVA_SUBSCRIPTION_PAYMENT_PROVIDER`. There is
no `if India:` anywhere, and a test parses the module's AST and fails if a
country or a vendor ever appears as a *value* the code compares against. (Its
first version grepped the text and flagged the *prose* — the docstring
explaining a Kenyan cooperative's timezone. The rule is about code, so the test
reads code.)

Currency comes from `organization.currency_code`, which the country registry
set at onboarding. It is never a parameter, never a default, and never a branch.

## 5. Provider recommendation

**Research only. No vendor was contacted, no account created, no credential
obtained, and nothing below was executed.** Fees, availability and regulatory
detail change; every figure a contract depends on must be confirmed with the
provider before it is relied upon.

First, a distinction that is easy to lose: DEMO-024 recommends a UPI/M-Pesa
payment rail, but that is **the dairy collecting from its own customers**. This
milestone is **Lacteva charging its tenants**. They are different money,
different counterparties and — probably — different providers.

**The structural finding is that no single provider serves India and Kenya
well.**

* *India.* Card-on-file recurring is constrained by RBI rules; the practical
  recurring rails are UPI AutoPay and e-NACH mandates, which domestic gateways
  support natively and most international ones do not.
* *Kenya.* M-Pesa is the rail that matters, and it has no native concept of a
  subscription — recurring means either a per-cycle STK push or a standing
  arrangement. Coverage generally comes through an aggregator rather than
  directly.
* *International SaaS providers* have the best subscription primitives by a
  distance, and the weakest fit with exactly these two local rails.

**Recommendation: plan for two providers side by side, not one.** That is why
the webhook route is addressed per provider (`/v1/payments/webhooks/{provider}`)
and why both unique constraints are scoped by provider — a second gateway can
be added, and a migration between them run, without a schema change.

**Recommended shortlist to evaluate** (in this order, and to be confirmed
commercially):

1. **India** — a domestic gateway with UPI AutoPay and e-NACH, hosted checkout
   and signed webhooks. Razorpay, Cashfree and PayU are the obvious candidates.
2. **Kenya** — an aggregator with real M-Pesa coverage and signed webhooks.
   Paystack, Flutterwave and DPO are the obvious candidates.
3. **Later markets** — an international provider for card-first markets, added
   as a third adapter rather than as a rewrite.

**Let the provider run the recurrence wherever it can.** Lacteva stays the
system of record for *entitlement*; the gateway executes *payment*. Building a
dunning engine to duplicate something a provider already does correctly is how
a dairy platform becomes a billing platform.

Selection criteria that actually decide it, rather than the marketing page:
signed webhooks with a documented verification scheme; a stable event id;
idempotent order creation; a server-side "fetch this payment" call (the
platform re-asks rather than trusting a redirect); settlement currency matching
the tenant's; and refund reporting, without which `refunded` cannot honestly
exist.

## 6. Payment flow

```
  quote          GET  /v1/organization/subscription/quote      server calculates
     ↓
  checkout       POST /v1/organization/subscription/checkout   row FIRST, then provider
     ↓
  hosted page    (the payer leaves)
     ↓
  confirmation   webhook  ──or──  POST .../checkout/refresh
     ↓
  verification   the platform asks the PROVIDER
     ↓
  activation     server-side, CAS, once
```

**The row is written before the provider is called.** A call lost in the
network then leaves something to reconcile, rather than money taken against no
record.

**`/checkout/refresh` takes no arguments, deliberately.** A browser returning
from a hosted checkout is a hint that something may have changed, not evidence
of what — so the most it can say is "look again". It cannot name a payment, an
amount or a status. The frontend may show success optimistically; the
authoritative state comes from the backend on the next read.

## 7. Webhook flow

```
POST /v1/payments/webhooks/{provider}      no authentication, by design
  → constant-time HMAC over the RAW body
  → look up the payment by (provider, provider_reference)
  → claim (provider, event_id) under a unique constraint
  → compare the reported amount with the STORED intent
  → CAS out of `pending`
  → activate
```

Four things it never does.

*It never reads a tenant from the payload.* The organization comes from the
`subscription_payment` row the provider reference names. A body claiming
`"organization_id"` is ignored — an unauthenticated caller naming a tenant is
the whole attack, and a test forges exactly that and asserts the named tenant
is untouched.

*It never takes an amount from the payload as truth.*

*It never creates a payment.* An event naming a reference the platform does not
know is dropped and **nothing is recorded**, so the endpoint cannot be used to
fill a table.

*It never acts twice.*

It returns **200 for a replay and for an unknown reference**, because a gateway
reads a non-2xx as "retry" and redelivering an event that was already applied
achieves nothing. It returns 401 and 404 without saying which check refused —
an attacker probing the endpoint learns from the difference.

It runs on a **platform session** (`core/rls.py`), because a webhook arrives
before the platform knows whose it is. It sets the tenant contextvar around the
work and restores it afterwards: `EventEnvelope.new` reads that contextvar, and
publishing without it would write outbox rows belonging to nobody — the defect
class DEMO-025 found.

Note it is deliberately **not** an `IdempotentRoute`. That route class keys on
a client-supplied `Idempotency-Key` header, and a gateway sends its own event
id instead; de-duplication belongs on that id, in the database, where a replay
cannot slip past a header nobody sent.

## 8. Subscription activation

`TRIALING → ACTIVE` (and `PAST_DUE → ACTIVE`) happens in exactly one function,
called from both the webhook and the server-initiated verification, so the two
cannot drift. It is reachable only when the provider reported `succeeded` **and**
the amount and currency match the stored intent.

It is not reachable from a success page, a query parameter, client-side
JavaScript, `localStorage`, or a manually supplied payment id. The operator
path from DEMO-026 (`.../subscription/activate`, `organization.subscription.manage`,
held by no tenant role) remains for the case where somebody at Lacteva
activates a subscription paid for outside the platform.

## 9. Renewal model

The model can represent a recurrence without running one:

| Field | Meaning |
|---|---|
| `started_on` | when the paid subscription began |
| `current_period_end` | the end of the current period **and** the next renewal date |
| `external_subscription_id` | the provider's recurring subscription, when it runs one |
| `status = cancelled` | the cancellation state |

One field for "period end" and "renews on", because two would be two chances to
disagree about the same day.

A `renewal.succeeded` event extends **from the period that is ending, not from
today**, so a confirmation that arrives late does not quietly shorten what was
paid for. Periods land on the calendar rather than in days: a subscription
starting 31 January renews 28 February, not 3 March.

**No recurring billing engine was built.** Where a provider runs the
recurrence, Lacteva records what it reported.

## 10. Expiration and grace policy

```
  trialing ──pay──▶ active ──renewal fails──▶ past_due ──grace ends──▶ expired
                      │                          │
                      └──── renewal succeeds ◀───┘
  any ──cancel──▶ cancelled
```

| State | May operate | May read | Notes |
|---|---|---|---|
| `trialing` | yes | yes | unlimited centres |
| `active` | yes | yes | until `current_period_end` |
| `past_due` | **yes** | yes | until `grace_ends_on` (default 14 days) |
| `expired` | no | **yes** | records intact |
| `cancelled` | no | **yes** | records intact |

**`past_due` operates.** That is the entire point of a grace period: the
subscription is in trouble, the dairy is not, and the platform does not confuse
the two. On the other side of a declined card is a dairy with milk arriving.

**Nothing is ever destroyed.** No data deleted, no user removed, no
administrator locked out, `can_read` always true. The only thing an expired
subscription cannot do is activate another collection centre.

The grace length is configuration (`LACTEVA_SUBSCRIPTION_GRACE_DAYS`), not a
constant, because it is a commercial policy rather than an engineering fact.

## 11. Centre-based pricing calculation

```
amount = quantize_money(unit_price × subscribed_centres, organization.currency)
```

Per collection centre — never per user, which would teach a dairy to share
logins and destroy the audit trail, and never per litre, which is the number a
dairy negotiates hardest and would make the bill seasonal.

`unit_price` comes from `subscription.price.<PLAN>.<CURRENCY>` in the existing
configuration store. **No price appears in source.** With none published, the
quote reports `unit_price: null` and checkout refuses — a zero or negative
price is treated as a misconfiguration, not a free plan, because opening a
checkout for nothing is worse than refusing one.

The client sends only the quantity. The portal re-asks the server whenever the
quantity changes and multiplies nothing itself.

## 12. Currency handling

From `organization.currency_code`, which the country registry set at
onboarding. India in INR, Kenya in KES, proven by a test that quotes both and
asserts neither the caller nor a default decided.

Money uses `quantize_money` / `format_money` from `core/money.py` — the scale
is a property of the currency, and no `Decimal("0.01")` was reintroduced.

**A defect found here by the PostgreSQL proof and invisible on SQLite:** the
columns are `NUMERIC(18, 6)`, so a payment just built in memory stringified as
`3600.00` while the same row read back from the database stringified as
`3600.000000`. Checkout would have shown one and the payment history the other,
about the same payment, and a dairy comparing them would have been right to ask
which it had been charged. Rendering now goes through `format_money`, which
asks the currency — the only thing that knows.

## 13. Security and RLS

Both new tables are tenant-owned, derived into the protected set from model
metadata, with policies installed by the same machinery as every other tenant
table. **68 policies present**, enabled and FORCED.

| Attempt | Result |
|---|---|
| No token on any payment endpoint | **401** |
| A `tenant-viewer` starting a checkout | **403** |
| Reading another organization's payments | empty — RLS refuses |
| Deleting another organization's payment under RLS | 0 rows |
| A webhook naming another tenant | that tenant untouched |
| An unsigned or wrongly-signed webhook | **401**, nothing written |
| A signed webhook naming an unknown reference | 200, nothing written |

The billing service is constructed from the **authenticated principal's**
tenant, so there is no request in which a caller can start a checkout for
somebody else — there is nowhere to say whose.

Payment history exposes the provider's public reference (what a support
conversation needs) and never a key, a signature or a payload; a test asserts
no secret-shaped word reaches a client, and another asserts no credential is
committed to the module.

## 14. Idempotency and concurrency

| Guarantee | Enforced by |
|---|---|
| One open payment per organization | `uq_subscription_payment_open` on `(tenant_id, open_key)` |
| One payment per provider reference | `uq_subscription_payment_provider_ref` |
| One action per provider event | `uq_subscription_payment_event` on `(provider, event_id)` |
| One terminal transition | CAS: `UPDATE … WHERE status = 'pending'` + rowcount |

`open_key` is nullable and holds `"open"` while pending. NULL does not collide
with NULL in PostgreSQL or SQLite, so one open intent is enforced by the
database while any number of settled ones coexist — portable, and not a partial
index the test stack could not run.

Every savepoint puts the `add` **inside** `begin_nested()`. Entering the
savepoint can autoflush a pending insert first, which would put the violation
outside it and poison the transaction — the bug DEMO-025 shipped and real
PostgreSQL found.

## 15. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — the nine-step proof on real PostgreSQL from
the `pgserver` wheel, no Docker and no root. **PASSED**, head `d5f1c8a72e46`,
**115 tests in step 3, 0 skipped**, 68 policies enabled and forced.

`tests/test_subscription_payment_concurrency_postgres.py` is in the proof's
explicit file list — a suite that is not listed is a suite that never runs —
and all eleven of its tests executed:

1. **eight concurrent checkouts open exactly one payment**, and every caller
   receives the *same* one; eight ids would be eight chances to be charged;
2. concurrent checkouts for *different* quantities resolve deterministically —
   one wins and the rest are refused, because two intentions cannot both be
   true and the platform must not average them;
3. two simultaneous deliveries of one event yield `activated` + `replayed`, one
   event row, one activation;
4. the same successful webhook, delivered five times, never extends the period
   twice;
5. one payment cannot activate two subscriptions;
6. a retry after a lost response charges nothing extra;
7. a trial cannot become two paid subscriptions;
8. a payment neither leaks nor deletes across tenants under the database's own
   RLS;
9–11. both tables FORCE row-level security, and all three unique constraints
   exist by name.

## 16. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **1778 passed**, exit 0 |
| `tests/test_subscription_payments.py` (new) | 45 |
| `tests/test_subscription_payment_concurrency_postgres.py` (new) | 11, on real PostgreSQL |
| Admin portal (`vitest`) | **262 passed** (19 files) |
| `subscription-page.test.tsx` | 10 (was 4) |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |

**The guards were mutation-checked, not merely exercised.** Disabling the
amount-mismatch check, the signature check and the replay ledger each made
exactly one test fail, and restoring each returned the suite to green. A guard
that cannot be shown to refuse is not evidence.

**One existing test was rewritten rather than deleted.** DEMO-026 asserted the
page had *no buttons at all*; DEMO-027 gives it a pay button, so that phrasing
became false. The guarantee it stood for did not, and the test now asserts it
precisely: a control may *ask* the server to do something, and no control
anywhere names a status, an amount or a currency.

## 17. Production verification

Deployed `main-6d7f747` to **https://dev.phoenixsoft.in** through the existing
path — git → GitHub Actions → ECR → `deploy.sh` (pull → backup → migrate →
deploy → verify → smoke). No flags, no forcing, no manual schema edits.

    schema at d5f1c8a72e46 (matches the image)
    database, redis, outbox, consumers, projections,
    notifications, jwt_keys, backups, background_workers — all healthy
    every tenant-owned table has a policy; policies are FORCED
    the API role lacteva_app is NOSUPERUSER/NOBYPASSRLS
    DEPLOYMENT VERIFIED — the platform is serving
    SMOKE TEST PASSED

11 containers healthy, dead-letter queue 0, undelivered outbox 0.

**The most important production result is a refusal.** The deployment has no
payment provider configured, and it says so rather than pretending:

| Attempt on production | Result |
|---|---|
| Quote a paid plan (India) | `payable: false`, `unit_price: null`, `amount: null`, reason given |
| `POST .../subscription/checkout` | **409** — "no payment provider is configured for this deployment" |
| `POST /v1/payments/webhooks/test` | **404** |
| `POST /v1/payments/webhooks/disabled` (the configured name) | **404** |
| `POST /v1/payments/webhooks/acme-pay` | **404** |
| `GET .../subscription/payments` with no token | **401** |
| `GET .../subscription/payments` as tenant admin | `[]` |

Every webhook path answers **404 on this deployment**, because the configured
provider is `disabled` and it refuses to parse anything. There is no request
that activates a subscription here, and the tables prove it: `subscription_payment`
and `subscription_payment_event` are **empty**, both with `relrowsecurity` and
`relforcerowsecurity` true, among **68 policies**.

Existing tenants are untouched — India `trialing`, 3 active centres; Kenya
`trialing`, 5 active centres; both `can_operate` and `can_read` true, no grace
window, no period end, and **no subscription moved off `trialing`**.

Month-to-date AWS cost is effectively nil (Cost Explorer reports a net of
~$0.0000003 with credits applied); the instance is the same `c7i-flex.large`.

**The browser walkthrough was NOT performed** — the Chrome extension is not
connected in this session, so the portal was verified by its route, its own
test suite and the API it calls, not visually. Same gap as DEMO-026, stated
rather than papered over.

## 18. Financial safety

The separation is physical, not conventional: `subscription_payment` is a
different table in a different module from `payment`. Two tests hold the wall
up — one counts dairy `payment` and `settlement` rows across a complete SaaS
payment and asserts they do not move, and one asserts the subscription module
never imports `modules.payment` or `modules.settlement` at all. A boundary that
is only a convention is a boundary until somebody is busy.

The migration is pure DDL: two tables created, one nullable column added, no
existing row read or written.

**Verified on production, before and after the deployment:**

| | Before | After |
|---|---|---|
| Invoiced | 809038.00 | **809038.00** |
| Receivables | 809038.00 | **809038.00** |
| Received | 444105.00 | **444105.00** |
| Settled (net) | 353417.50 | **353417.50** |
| Collections | 534 | **534** |
| Settlements | 84 | **84** |
| Invoices / receipts / dairy payments | 31 / 24 / 42 | **31 / 24 / 42** |
| Organizations / active centres | 5 / 10 | **5 / 10** |
| Subscriptions | 2 | **2** |

The only count that moved is users, 104 → 105: the deployment's own smoke test
registers a throwaway account and deletes nothing, by design. A verified backup
was taken first — 66 tables, 41,497 rows, 26.6 MB, `verified: true`, plus a
second explicit verify pass — on top of the one `deploy.sh` takes itself.

## 19. Real versus test functionality

**REAL — code that would work against a contracted gateway**

* The provider boundary, the registry, and configuration-driven selection.
* Server-side amount calculation, currency resolution, and money quantization.
* The complete payment lifecycle: quote → checkout → verification →
  activation → renewal → grace → expiry.
* Webhook signature verification, replay defence, tenant resolution, amount
  re-checking, CAS transitions.
* RLS, permissions, cross-tenant isolation, payment history.
* Startup validation that refuses a misconfigured deployment.

**TEST / DEMO only**

* `TestPaymentProvider` — deterministic, takes no money, refused in production
  by settings validation. Every payment in every test is one of these.
* The `checkout_url` it returns points at `payments.test.invalid`.

**NOT IMPLEMENTED**

* **No real payment provider. No customer can pay Lacteva.** No account exists,
  no credential exists, no gateway was contacted, and nothing in this milestone
  moved a single unit of currency.
* `refunded` — nothing can confirm a refund without a provider that reports
  one. The ledger is shaped to receive it.
* No notification consumer for the payment events (see below).
* No dunning, proration, subscription invoicing, tax handling, or usage
  metering.
* No self-service plan change or upgrade/downgrade proration.
* No renewal *scheduler*: where a provider does not run the recurrence, nothing
  in Lacteva creates the next payment.

## 20. Exact production configuration still required

To enable real payments, in this order:

1. **A commercial decision on price**, per plan and per currency. Until then
   every deployment reports `price: null` and checkout refuses.
2. **A contracted provider** for each market (§5), with a merchant account.
3. **An adapter** — one class implementing `PaymentProvider`, one line in
   `_build`, one `Literal` value in `Settings`. Nothing in the domain moves.
4. **Deployment configuration**, never source control:

   ```
   LACTEVA_SUBSCRIPTION_PAYMENT_PROVIDER=<provider>
   LACTEVA_SUBSCRIPTION_PAYMENT_WEBHOOK_SECRET=<from the provider>
   LACTEVA_SUBSCRIPTION_GRACE_DAYS=14          # optional
   ```

   plus whatever credential the adapter needs. The platform **refuses to
   start** if a provider is selected without a webhook secret, and refuses
   outright if `test` is selected in production.
5. **The webhook URL registered with the provider**:
   `https://<host>/v1/payments/webhooks/<provider>`.
6. **The price published** per currency in the configuration store:
   `subscription.price.LACTEVA_STANDARD.INR`, `…KES`.
7. **An executed proof against the real gateway in its sandbox.** Everything in
   this milestone is evidence about the platform. None of it is evidence that a
   particular vendor behaves as documented, and by the standing rule here, that
   is not proven until it has been run.

## 21. Known limitations

* **Customers cannot pay.** Stated once more because it is the thing most
  likely to be misremembered.
* `past_due` is reachable in production only once a real provider can report a
  failed renewal. Today only the test provider can drive it.
* Grace is a fixed number of days per deployment, not per plan or per tenant.
* Cancellation is immediate; there is no "cancel at period end".
* One open payment per organization. A dairy wanting to pay two invoices at
  once must settle one first — deliberate, and revisit it if it ever bites.
* No notification is sent on payment success, failure or expiry. The events are
  published to the outbox; no consumer reads them, because every messaging
  provider is `disabled` on this deployment and a consumer would only produce a
  refusal in the notification history. The wiring is one consumer when a
  channel is live.
* The centre quantity is chosen by the customer and is not forced to match the
  centres actually active — an under-subscribed dairy sees an overage and keeps
  operating, which is the DEMO-026 policy and deliberate.
* No admin console: Lacteva still cannot see all tenants' commercial standing
  in one place.

## 22. Recommended DEMO-028

**Recommended: the operator's console and trial/payment lifecycle
communication** — the milestone DEMO-026 already recommended, now with more to
show. Lacteva cannot sell a subscription it cannot see: today the only way to
know a tenant's plan, trial end, active centres, payment history and grace
status is to be that tenant. Concretely: a platform-admin view across all
organizations, plus a consumer on the events this milestone publishes
(`subscription.payment-succeeded.v1`, `…payment-failed.v1`, `…activated.v1`,
`…renewed.v1`, `…past-due.v1`) with templates in all four languages, wired to
whichever channel a tenant chose. That needs no vendor and no commercial
decision.

**Then: the first real provider adapter**, once a price and a contract exist —
§20 is the checklist, and step 7 is the part that actually proves it.

**Not recommended yet:** proration, usage metering and multi-currency
settlement reporting. All three are only meaningful once real money has moved
at least once.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-027: a provider-independent payment boundary, server-calculated centre-based amounts, verified activation, a replay-safe webhook, and a grace period that keeps a dairy working. Deterministic test provider only — no gateway contracted, and customers cannot pay. |
