---
id: DEMO-028-FINAL
title: DEMO-028 — Farmer Settlement & Customer Invoice Delivery
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-027-FINAL, DEMO-025-FINAL, DEMO-023-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-028 — Farmer Settlement & Customer Invoice Delivery

Both journeys already ran. This milestone is about what they were not saying,
and about one thing the platform was claiming that it could not know.

---

## 1. Survey findings

**DEMO-025 had already built both journeys end to end.** The honest survey
result is that this milestone is not "build settlement and invoice messaging"
but "close the gaps in messaging that already runs":

| Capability | State before DEMO-028 |
|---|---|
| `NotificationService.dispatch` — the only path from fact to message | complete |
| Provider registry, six provider kinds, four channels | complete |
| Template catalog — 32 templates; both journeys in ar/en/hi/sw on sms and whatsapp | complete |
| Tenant channel choice — `notification.channel.<template_key>` | complete |
| Idempotency — `(event_id, template_key, channel)` unique + savepoint | complete |
| Business dates carried on both events | complete (DEMO-025 fixed the UTC-slice bug) |
| Language: organization default, narrowed to the recipient's own | complete |
| Portal history + template preview; mobile notifications screen | complete |
| Recipient directory, phone masking, retry classification | complete |

**Six gaps, and the first two are defects.**

1. **The portal claimed "Delivered."** `notifications/page.tsx` labelled the
   count of `sent` as *Delivered*. `sent` means the provider accepted the
   request; no adapter in this platform receives a delivery receipt. It was the
   headline figure on the screen, where an operator reads it as proof a farmer
   was reached.
2. **`DeliveryResult.status` was discarded.** Adapters have returned the
   gateway's own word (`accepted` / `sent` / `delivered` / `unknown`) since
   MSG-001 and nothing stored it — so the platform could not distinguish "the
   gateway took it" from "the gateway says it arrived" even when told.
3. **The settlement slip had no quantity.** A farmer was given an amount with
   no indication how much milk it was for.
4. **The bill showed only `amount_due`.** With anything carried forward, a
   household could not tell this period's charge from the total owed.
5. **Template language gaps.** `invoice_issued` had no Swahili WhatsApp
   template, so a Kenyan dairy that chose WhatsApp got English bills while its
   SMS bills were Swahili — the fallback is silent. Both email templates were
   English-only, and `push`, the *default* channel for a bill, had no Hindi or
   Arabic.
6. **No direct source link.** A notification recorded `event_id` but not the
   settlement or invoice, so "what did STL-2026-000042 tell this farmer?" meant
   walking `event_outbox` payloads.

**Deliberately not added: deductions.** `adjustments_amount` is fixed at zero
by BR-0011 until the bonus and penalty engines exist. A permanently-zero line
invites the question "why is this here?", and DEMO-025 already shows gross
beside net for exactly that reason.

## 2. Existing capabilities reused

Everything in the table above. **No second notification system, no second
provider boundary, no second template engine, no second portal page and no
second mobile architecture.** The changes are: three nullable columns, two
event payloads gaining fields they can already read, ten templates, one
template-engine syntax addition, and wording on one existing screen.

## 3. Farmer settlement journey

```
settlement finalized (existing, unchanged)
      ↓  settlement.finalized.v1  — now carries quantity + unit
notification-dispatch consumer (existing)
      ↓  template + tenant channel + organization language
NotificationService.dispatch (existing, idempotent)
      ↓
provider adapter → external channel
      ↓
notification row: status, provider_status, source_type/source_id
```

The statement now says **how much milk the money is for**. `quantity` is the
sum of `settlement_line.quantity` and `quantity_unit` is the lines' own unit —
read at finalize time, stored nowhere, changing nothing. Mixed units report no
quantity at all rather than adding litres to kilograms, because a meaningless
number on a farmer's statement is worse than a missing one.

Every other figure is exactly what it was: settlement number, period, gross,
net, line count, currency — all read from the finalized settlement.

## 4. Customer invoice journey

Identical shape, from `sales.invoice-issued.v1`. The bill now carries
**quantity delivered** and **brought-forward balance**, both authoritative on
the invoice. `amount_due` is this period's total plus anything carried; a
household with a balance was shown one number matching neither, with no way to
tell which.

A zero brought-forward renders **nothing** — "brought forward: 0.00" is noise.

## 5. Message architecture

```
FINANCIAL DOMAIN        settlement / billing — unchanged
      ↓                 publishes a fact, and has never heard of a channel
AUTHORITATIVE RECORD    the event payload: numbers read, never computed
      ↓
MESSAGE BUILDER         consumers/notification_dispatch.py — declarative
      ↓                 mapping; writes no message string of its own
NOTIFICATION SERVICE    template + language + channel + idempotency
      ↓
PROVIDER ADAPTER        the only code that knows a vendor exists
      ↓
EXTERNAL CHANNEL
```

The settlement and billing modules gained **no import** from notification, and
the notification module gained **none** from settlement or billing. The
financial domain still does not know that WhatsApp exists.

## 6. Templates

**39 templates**, up from 32. The addition to the engine is an *optional
segment*:

```
"Your bill {number} is {amount}[[ for {quantity} {quantity_unit}]]."
```

A segment renders only when every variable inside it is present and non-empty;
otherwise it disappears, brackets and all. A variable outside a segment is
still **required**, and a missing one is still an error — the guarantee that
stops half a sentence reaching a farmer is untouched.

**This exists because of a real hazard, not for elegance.** A retry re-renders
from the payload *stored* on the notification row, so adding a required
variable to a template retroactively breaks every notification already in the
table. Production held **17 retryable `invoice_issued` rows** whose payloads
predate this milestone; they would have begun failing on a template error
instead of their real one. With optional segments, old payloads render exactly
as they did and new ones carry the extra line.

## 7. Languages

English, Hindi, Arabic and Swahili, and **every business template now offers
all four on every channel it supports**:

| | sms | whatsapp | email | push |
|---|---|---|---|---|
| `settlement_finalized` | ar en hi sw | ar en hi sw | ar en hi sw *(was en)* | — |
| `invoice_issued` | ar en hi sw | ar en hi sw *(was ar en hi)* | ar en hi sw *(was en)* | ar en hi sw *(was en sw)* |

A test asserts this parity, so the gap cannot reopen: **a tenant switching
channel must not also switch language.** The language itself is unchanged — the
organization's default, narrowed to the recipient's own where the directory or
device knows one. It is never a parameter of the event.

## 8. Currency handling

Unchanged and reused: the amount is the record's own, in
`organization.currency_code`, at the precision it was stored with. No symbol is
invented, no country consulted, and no formatting introduced — the PostgreSQL
proof asserts `18562.50` survives the round trip in both INR and KES.

## 9. Business-date handling

Unchanged and reused. Both events carry the record's **own business dates**,
and the proof re-asserts the boundaries: 19:00 UTC on 31 August is already 1
September in Bengaluru; 20:30 UTC is still 31 August in Nairobi and 21:30 is
not. A statement dispatched after local midnight still names the period it
settles.

## 10. Provider behaviour

Two columns, because they are two facts:

| | meaning |
|---|---|
| `status` | what **Lacteva** did: `pending` → `sent` / `failed` → `dead` |
| `provider_status` | what the **gateway** said: `accepted` \| `sent` \| `delivered` \| `unknown` |

`sent` means the gateway accepted the request. **Every adapter in this platform
reports `accepted` and none receives a delivery receipt**, so nothing claims
`delivered`. The portal now reads "Sent to provider", "queued", "failing" and
"gave up", and a test fails if the word *Delivered* appears anywhere on that
screen.

A disabled provider **refuses loudly**: the notification is recorded as failed
with a reason, `sent_at` stays null, `provider_status` stays null. Nothing is
silently dropped and nothing reports success — proven on PostgreSQL.

## 11. Idempotency

Unchanged and reused: `uq_notification_event` on `(event_id, template_key,
channel)`, claimed inside a savepoint with the `add` **inside** it. A repeat
returns `None` rather than sending. Proven again here under real concurrency:
eight concurrent dispatches of one finalized settlement produce one row and
**one gateway call** — every extra call is a charge and a farmer told twice
about the same money.

## 12. Delivery records

Everything §11 of the work order asks for, and the last two are new:

tenant · message type (`template_key`) · **source record (`source_type` /
`source_id`)** · channel · recipient (masked by the existing convention) ·
template + language · provider · status · **provider's own status** ·
provider reference · created / sent / failed timestamps · failure reason ·
attempt count.

No provider payload is stored, no credential, no signature. `secret_payload` is
still cleared the moment a notification reaches a terminal state.

## 13. Security and RLS

Unchanged conventions, re-proven for the new columns: `notification` is
tenant-owned, RLS enabled and **forced**, among 68 policies. On PostgreSQL, a
second tenant querying with no filter at all sees zero rows, cannot read the
statement text, and deletes zero rows. Unauthenticated reads are 401 and the
existing permission checks are untouched.

## 14. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — **PASSED**, head `e8b2a4c60d17`, **136 tests
in step 3** (up from 115), 0 skipped, 68 policies.

`tests/test_statement_delivery_postgres.py` is in the proof's explicit file
list — a suite that is not listed is a suite that never runs — and covers all
twelve properties the work order names: statement creation, bill creation,
duplicate settlement request, duplicate invoice request, eight-way concurrent
dispatch (one row, one gateway call), provider failure, retry, cross-tenant
isolation, language selection across four languages, currency rendering in INR
and KES, the India/Kenya business-date boundary, and disabled-provider
behaviour.

## 15. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **1820 passed**, exit 0 |
| `tests/test_statement_delivery.py` (new) | 21 |
| `tests/test_statement_delivery_postgres.py` (new) | 21, on real PostgreSQL |
| Admin portal (`vitest`) | **265 passed** (20 files) |
| `notifications-page.test.tsx` (new) | 3 |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |
| Lint, format, tsc, eslint, build, docs, xref | all green |

**Four guards mutation-checked**, each making exactly one test fail: treating
optional segments as required, removing the Swahili WhatsApp template, not
storing `provider_status`, and dropping quantity from the settlement event.

## 16. Production verification

Deployed `main-948933e` to **https://dev.phoenixsoft.in** through the existing
path — git → GitHub Actions → ECR → `deploy.sh`. No flags, no forcing, no
manual schema edits. Schema at `e8b2a4c60d17`, matching the image; all nine
components healthy; 11 containers healthy; dead-letter queue 0; undelivered
outbox 0. `SMOKE TEST PASSED`.

**Nothing on production claims a delivery:**

| | |
|---|---|
| Rows claiming `provider_status = 'delivered'` | **0** |
| Rows with no provider claim at all | **251** (all of them — they predate the column, which is the honest value) |
| Rows with `status = 'sent'` | 12 |

`provider_status` and `source_type` read `null` on every pre-existing row and
the API returns them as such, on both tenants. No backfill was performed:
nothing recorded before this migration knows what a provider claimed, and
inventing one would put an unobserved fact in the audit trail.

**Notification configuration is unchanged** — `config_entry` holds **zero**
`notification.channel.*` rows, so no tenant's channel moved. Both messaging
providers on the deployment remain `disabled`
(`LACTEVA_NOTIFICATION_SMS_PROVIDER=disabled`,
`LACTEVA_NOTIFICATION_EMAIL_PROVIDER=disabled`).

**No external message was delivered by this milestone, and none is reported as
delivered.** The India tenant's history holds 25 settlement messages and
Kenya's 49, every one of them `dead` — the correct outcome for a deployment
with no gateway, visible rather than silent.

RLS on `notification` is enabled and **forced**, among 68 policies.

Month-to-date AWS cost is effectively nil (~$0.0000003 net with credits
applied); same `c7i-flex.large`.

**Two things stated rather than glossed.** The browser walkthrough was **not
performed** — the Chrome extension is not connected in this session, so the
portal's corrected wording was verified by its own test suite and the API, not
visually. And both production tenants are configured `en-IN` / `en`, so no
Hindi, Arabic or Swahili message exists in production data: the language work
is proven by tests and by the PostgreSQL proof, not by production content.

## 17. Financial safety

The messaging layer **reads** financial truth; it does not become it. Asserted
rather than asserted about: a test snapshots settlement, invoice, payment and
receipt counts plus settlement net and invoiced totals, runs the complete
messaging pipeline including a retry, and asserts the snapshot is identical.

No calculation was touched. The settlement and billing changes are two **reads**
(`_sum_quantity`, `_sum_invoice_quantity`) publishing figures onto events; no
column was written, no total recomputed, no migration touched a financial
table.

**Verified on production, before and after the deployment:**

| | Before | After |
|---|---|---|
| Invoiced | 809038.00 | **809038.00** |
| Receivables | 809038.00 | **809038.00** |
| Received | 444105.00 | **444105.00** |
| Settled (net) | 353417.50 | **353417.50** |
| Paid out to suppliers | 168675.50 | **168675.50** |
| Collections / settlements | 534 / 84 | **534 / 84** |
| Invoices / customer receipts / receipts | 31 / 24 / 36 | **31 / 24 / 36** |
| Supplier payments / customer payments | 42 / 24 | **42 / 24** |
| Notifications | 251 | **251** |

Every figure identical, including the notification count — deploying produced
no message. A verified backup was taken first (68 tables, 41,515 rows,
`verified: true`, plus a second explicit verify pass), on top of the one
`deploy.sh` takes itself.

## 18. REAL versus TEST

**REAL**
* Both journeys, end to end, from a finalized settlement and an issued invoice.
* Quantity, brought-forward balance, source linkage, provider status.
* 39 templates in four languages; tenant channel selection; organization
  language and currency.
* Idempotency, retry, failure classification, RLS.
* Every guard, executed — including on real PostgreSQL.

**TEST / DEMO**
* Every message in every test goes to a deterministic in-process fake
  (`_RecordingProvider`, `_CountingProvider`, `_FlakyProvider`,
  `DisabledProvider`). **No external message was sent by this milestone.**

**NOT IMPLEMENTED**
* **No production messaging provider is enabled.** Every channel on the live
  deployment is `disabled`, so no farmer and no household received anything.
* No delivery receipts. No adapter receives them, so `delivered` is a value the
  column can hold and nothing currently writes.
* No PDF or attachment: the statement is a message, not a document.
* No per-recipient opt-out or quiet hours.
* No mobile change — the existing farmer, customer-portal and notification
  journeys already cover this and needed nothing.

## 19. Known limitations

* Nothing is delivered in production, and nothing pretends to be.
* `delivered` remains unreachable until an adapter receives receipts; the
  column and the portal wording are ready for it.
* Mixed measurement units on one settlement or invoice suppress the quantity
  line rather than converting.
* Deductions are absent because BR-0011 fixes them at zero.
* No due date on a bill — `customer_invoice` has no such column, and inventing
  one would be inventing a commitment.
* The recipient directory is still built from supplier events only; households
  are reachable because the invoice event carries their number, which works and
  is not a directory.
* Email is still address-only plain text: no HTML, no attachments.

## 20. Recommended DEMO-029

**Recommended: delivery receipts and the reachability gap.** Two things follow
directly from what this milestone exposed. First, a provider webhook that
records real delivery status — the column, the wording and the vocabulary now
exist, and DEMO-027 built a signature-verified, replay-safe webhook boundary
that this can reuse rather than reinvent. Second, the reachability question the
history can now answer but nobody asks: *which* farmers and households have no
usable address at all, before a settlement run rather than after it. A dairy
that discovers on payment day that 30 farmers have no phone number has
discovered it too late.

**Then: a settlement statement as a document.** A message tells a farmer the
total; a PDF passbook page shows the collections behind it. The receipt module
already renders real PDFs (PROD-001), so this is composition rather than new
machinery.

**Not recommended yet:** per-recipient preferences and quiet hours. Both are
only meaningful once real messages are actually being delivered.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-028: a farmer is told how much milk the money is for, a household can tell this period's charge from what it owed, both in their own language on every channel — and the portal stopped calling an accepted request a delivery. |
