---
id: DEMO-032-FINAL
title: DEMO-032 — Commercial/Regulatory Messaging Foundation & Template Registry
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-031-FINAL, DEMO-029-FINAL, DEMO-025-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-032 — Commercial/Regulatory Messaging Foundation & Template Registry

Separating two concerns: what a regulator and a vendor will require, and what
Lacteva can actually say. **No vendor was selected, contacted or credentialed,
and no message was sent.**

---

## 1. What already existed

A template registry, in all but name. `templates.py` holds **41 templates**
with key, channel, language, title, body, declared variable order and optional
segments; `get_template` / `render` / `catalog` / `languages_for` are its API;
the portal already lists and previews them; and DEMO-031 added
`vendor_template_for()` reading `notification_vendor_templates` from deployment
configuration.

Also complete and reused unchanged: channels, the provider abstraction and
registry, dispatch, delivery state, DEMO-029's webhook security, tenant channel
configuration, reachability, and both the settlement and invoice journeys.

**What it lacked** — business purpose, active/version, provider-mapping
*status*, and one real defect:

> **An unknown variable was silently ignored.** `render(template, {"not_a_variable": …})`
> returned successfully. So renaming a variable, or adding a figure a template
> did not yet show, produced a message that reached a farmer looking complete
> and missing the number somebody had just added for them.

## 2. Commercial and regulatory research

**No vendor or regulator was contacted.** Everything below is from public
documentation as it stood at the time of writing, classified exactly as §2
requires. **Every commercial term and every current-rule detail must be
confirmed before contracting or filing** — regulation in both markets has moved
repeatedly and none of it is verifiable from here.

## 3. India requirements

### SMS

* **[PUBLIC]** Commercial SMS is governed by TRAI's **DLT** (Distributed Ledger
  Technology) regime. An enterprise registers as a **Principal Entity**,
  registers its **Header** (sender ID), and registers **content templates**;
  traffic is matched against those registrations at the operator.
* **[PUBLIC]** Templates are registered by **category** — service/transactional
  versus promotional — and the category governs what may be sent and when.
* **[PUBLIC]** A template contains fixed text with variable placeholders;
  arbitrary free text does not pass. This is the same structural constraint
  WhatsApp imposes, arriving from a regulator instead of a platform.
* **[INFERRED]** Lacteva's messages — settlement finalised, invoice issued,
  payment recorded — are service/transactional in nature, being sent to an
  existing counterparty about an existing transaction.
* **[UNKNOWN]** The current registration fee schedule, turnaround times,
  per-message DLT charges, the exact category taxonomy in force today, and
  whether any of Lacteva's wordings would be rejected on review.

### WhatsApp

* **[PUBLIC]** The WhatsApp Business Platform requires **business
  verification** through Meta Business Manager, a **registered phone number**
  dedicated to the platform, and **pre-approved message templates** for any
  business-initiated message.
* **[PUBLIC]** Templates carry a **category** (utility / authentication /
  marketing) and are submitted for review; parameters are **positional**.
* **[PUBLIC]** Free-form messages are permitted only inside a **24-hour
  customer-service window** opened by the customer.
* **[INFERRED]** Lacteva's messages are *utility* category: they concern a
  transaction the recipient is party to.
* **[UNKNOWN]** Current per-conversation pricing and category rules, review
  turnaround, and whether a template carrying an *optional* line would be
  approved at all (see §11 — the answer matters).

## 4. Kenya requirements

### SMS

* **[PUBLIC]** Kenya's telecommunications sector is regulated by the
  **Communications Authority of Kenya**; bulk-SMS provision is a licensed
  activity.
* **[INFERRED]** An alphanumeric **sender ID must be registered** through the
  provider or the operators before traffic flows, in the same shape as India's
  header registration but under a different regime.
* **[UNKNOWN]** The current registration process, its cost and turnaround,
  whether content templates must be pre-registered as in India, and the
  applicable data-protection obligations under the **Data Protection Act 2019**
  for sending transaction details by SMS.

### WhatsApp

* **[PUBLIC]** The WhatsApp Business Platform requirements are Meta's and are
  **the same everywhere**: business verification, a registered number, approved
  templates, positional parameters, the 24-hour window. Nothing about them is
  Kenya-specific.
* **[UNKNOWN]** Kenyan pricing tier, local BSP availability and terms, and any
  Data Protection Act implications specific to WhatsApp.

**[INFERRED] and worth stating plainly:** both markets require the same *shape*
— a registered sender identity and pre-registered template content. Lacteva's
message catalog is therefore not merely an implementation detail; it is the
artefact that gets filed with a regulator and a platform. That is why this
milestone built the registry.

## 5. Provider comparison

**No vendor was contacted, no account created, nothing purchased.** Rows are
what public documentation establishes about *capability*; every commercial cell
is `[UNKNOWN]` because it is not verifiable from here and changes.

| | Twilio | Infobip | Africa's Talking | Gupshup | MSG91 |
|---|---|---|---|---|---|
| India SMS | [PUBLIC] offered | [PUBLIC] offered | [UNKNOWN] | [PUBLIC] domestic | [PUBLIC] domestic |
| Kenya SMS | [PUBLIC] offered | [PUBLIC] offered | [PUBLIC] core market | [UNKNOWN] | [UNKNOWN] |
| India WhatsApp | [PUBLIC] BSP | [PUBLIC] BSP | [UNKNOWN] | [PUBLIC] BSP | [PUBLIC] BSP |
| Kenya WhatsApp | [PUBLIC] BSP | [PUBLIC] BSP | [UNKNOWN] | [INFERRED] same platform | [UNKNOWN] |
| SMS API | [PUBLIC] HTTPS/REST | [PUBLIC] HTTPS/REST | [PUBLIC] HTTPS/REST | [PUBLIC] HTTPS/REST | [PUBLIC] HTTPS/REST |
| WhatsApp API | [PUBLIC] | [PUBLIC] | [UNKNOWN] | [PUBLIC] | [PUBLIC] |
| Delivery receipts | [PUBLIC] status callbacks | [PUBLIC] | [PUBLIC] | [PUBLIC] | [PUBLIC] |
| Webhooks | [PUBLIC] | [PUBLIC] | [PUBLIC] | [PUBLIC] | [PUBLIC] |
| Sandbox / test | [PUBLIC] test credentials + WhatsApp sandbox | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] |
| Template support | [PUBLIC] | [PUBLIC] | [UNKNOWN] | [PUBLIC] + DLT | [PUBLIC] + DLT |
| Sender registration help | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [INFERRED] DLT-native | [INFERRED] DLT-native |
| Pricing model | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] | [UNKNOWN] |
| Implementation complexity | [INFERRED] low — one adapter, both channels, both markets | [INFERRED] low | [INFERRED] low for SMS, unproven for WhatsApp | [INFERRED] low, India-first | [INFERRED] low, India-first |
| Multi-country suitability | [INFERRED] high | [INFERRED] high | [INFERRED] Kenya-strong | [INFERRED] India-strong | [INFERRED] India-strong |

## 6. Preferred candidate

**[INFERRED] Twilio, as the candidate to evaluate first — not as a selection.**
Its public documentation establishes SMS and WhatsApp in both markets, status
callbacks, and a documented test/sandbox path, which means **one adapter, one
contract, one webhook shape** and the fewest moving parts for a platform whose
whole design goal is vendor-neutrality. Infobip is close enough on published
capability that the decision may well come down to price and support, neither
of which is knowable here.

## 7. Alternative candidate

**[INFERRED] a two-adapter split: an India-domestic gateway (Gupshup or MSG91,
both DLT-native) plus Africa's Talking for Kenya.** More operational surface —
two contracts, two credentials, two registrations — but plausibly better local
support and pricing in each market, and the existing provider abstraction
already supports running two adapters side by side. This is the option to take
if the single-vendor pricing turns out to be poor in either market.

## 8. Unknowns requiring vendor or regulator confirmation

Before contracting, confirm — none of these is knowable from public
documentation alone:

1. Per-message and per-conversation **pricing** in both markets, including DLT
   charges.
2. Whether the candidate will act as, or assist with, **DLT principal-entity
   and header registration**, and the turnaround.
3. **Kenyan sender-ID registration**: process, cost, who files it.
4. **WhatsApp template review**: turnaround, and specifically whether a
   template containing a conditionally-present line can be approved (§11).
5. **Sandbox terms**: whether a test environment exists that exercises delivery
   receipts, not only sends.
6. **Data-protection obligations** in Kenya for transmitting settlement amounts
   by SMS.
7. Support model and escalation path for a delivery failure affecting a payment
   run.

**Reject a candidate if:** it cannot supply delivery receipts by webhook (the
platform's `delivered` state becomes permanently unreachable); it cannot
support both channels in both markets without a second contract *and* the
second contract is not acceptable; it requires Lacteva to hold message content
in its systems in a way that conflicts with tenant isolation; or its template
review cannot accommodate the message set in §10.

## 9. Template registry

**Extended, not replaced** — §5's first branch. `Template` gained `version`,
`active` and a `purpose` derived from a new `PURPOSES` map; `variables_for()`
answers what a key may legitimately be given; and `NotificationService.registry()`
is the read model.

It is **read-only, and that is a decision rather than an omission.** A template
is code: reviewed, tested, shipped, and re-rendered months later when a message
is retried. A database-editable message that a farmer receives about their
money is a change nobody reviewed — and, once a wording is approved by a
regulator or by Meta, an editable copy is a wording that has silently diverged
from the approved one. A test asserts no endpoint can write a template.

## 10. Message types and variables

Registered from what the product **actually has**. Twelve keys, 41 templates,
no invented journey:

| Journey | Purpose | SMS | WhatsApp | Email | Push |
|---|---|---|---|---|---|
| `settlement_finalized` | farmer's settlement is final | ar en hi sw | ar en hi sw | ar en hi sw | — |
| `invoice_issued` | customer's bill is ready | ar en hi sw | ar en hi sw | ar en hi sw | ar en hi sw |
| `payment_completed` | farmer payment executed | en | — | — | — |
| `receipt_available` | payment receipt ready | en sw | — | — | — |
| `customer_payment_recorded` | customer payment recorded | — | — | — | en sw |
| `milk_rejected` | a collection was rejected | en | — | — | — |
| *platform messages* (`invitation`, `invitation_accepted`, `password_reset`, `supplier_registered`, `supplier_archived`, `price_unavailable`) | account and access | varies | — | varies | — |

The last row is marked **non-business** in the registry: a password reset is not
something a dairy sends its farmers, and the distinction is the same one
DEMO-025 drew for tenant channel selection — and the same line a regulator
draws between service messaging and everything else.

**Variable safety (§8), all enforced by `render`:**

| Rule | Behaviour |
|---|---|
| Missing required variable | rejected — half a sentence is worse than none |
| **Unknown variable** | **now rejected** — this was the defect |
| Ordering | the template's declared order, deterministic |
| Channel mismatch | rejected, not guessed |
| Optional-segment variable | known; supplying it switches the segment on |

"Unknown" means *no template with this key displays it, on any channel or in
any language* — not "this one channel". One dispatch builder feeds every
channel of a key: `invoice_issued` supplies `period` for push and
`previous_balance` for WhatsApp and email, and SMS uses neither. The first
draft of the check required each channel's exact set and three delivery tests
said so immediately.

## 11. WhatsApp template handling — and the finding

Positional parameters are the template's declared variable order, carried to
the boundary by DEMO-031's `OutboundMessage.parameters`. The vendor's template
name is configuration (`notification_vendor_templates`) and never business
logic.

**The registry surfaced a real conflict that nothing had previously stated:**

> **All 8** business WhatsApp templates are currently **unusable as approved
> WhatsApp templates.**

An approved template has a **fixed parameter count**. DEMO-028 added *optional
segments* — the quantity line on a settlement slip, the brought-forward balance
on a bill — which appear only when they mean something, and which exist because
a retry re-renders from a payload that may predate them. Both designs are right
on their own terms and they are incompatible.

```
invoice_issued        ar en hi sw   cannot be an approved template
settlement_finalized  ar en hi sw   cannot be an approved template
```

The registry reports this per template with the reason, and a test asserts it
keeps reporting it. **It is not resolved here**, because the resolution is a
product decision with two legitimate answers: approve a template that always
carries the line and always supplies a value, or approve one that omits the
line on WhatsApp and keeps it on SMS and email. Choosing unilaterally would be
inventing business behaviour, which §6 forbids.

## 12. Multi-language

Unchanged and now visible. English, Hindi, Arabic and Swahili; language remains
a property of the recipient and the template, resolved from the organization
and narrowed to the recipient's own. **No country appears anywhere** — asserted
by a test over the registry's own output — and nothing assumes a production
tenant has every language configured. Both production tenants are `en-IN`/`en`
today and the registry says nothing about that either way.

## 13. Provider mapping

Provider-neutral, exactly as §11 asks:

```
Lacteva template : settlement_finalized
Channel          : whatsapp     Language: en
Provider         : <not selected>
Provider template: <not configured>
Status           : NOT_CONFIGURED
```

Three states: `NOT_APPLICABLE` (SMS, email and push send text — a vendor
template name is only meaningful where a vendor requires one, and calling these
"unmapped" would invent 33 problems nobody has), `NOT_CONFIGURED`, and
`CONFIGURED`. **The application works correctly with no mapping at all** — 8
unmapped WhatsApp templates on the current deployment, and nothing is broken by
it.

## 14. Portal changes

One panel on the existing notifications page, beside DEMO-031's gateway panel.
Per template: key, purpose, channel, language, variable counts, version/status,
and provider mapping — with the WhatsApp blocker spelled out on the rows it
affects. A filter defaults to business messages. It says plainly that templates
are not editable there and why.

**No credential and no gateway URL**, asserted by a test that sweeps the
rendered page.

## 15. Security and RLS

**Templates are process-wide because they are code** — the existing
architecture, and §13's explicit allowance. There is therefore nothing
tenant-shaped in the registry to isolate, and a test asserts two tenants
receive byte-identical responses containing no tenant data.

What *is* per-tenant is the channel a dairy chose, which lives in the
configuration store behind RLS and is **not** exposed by the registry — proven
again on PostgreSQL. Unauthenticated access is 401; no write path exists;
`config_entry` holds no credential-shaped key.

## 16. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — **PASSED**, **199 tests in step 3** (up from
184), 0 skipped, 69 policies.

`tests/test_template_registry_postgres.py` is in the proof's explicit file
list. It covers §14's list except template creation, update and concurrent
modification — **there is no write path, so there is nothing to prove about
writes**, and the file says so rather than fabricating a test. What is proven
concurrently is that the registry is a pure read: eight simultaneous callers,
one byte-identical answer.

## 17. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **2011 passed**, exit 0 |
| `tests/test_template_registry.py` (new) | 28 |
| `tests/test_template_registry_postgres.py` (new) | 15, on real PostgreSQL |
| Admin portal (`vitest`) | **281 passed** (20 files) |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |
| Lint, format, tsc, eslint, build, docs, xref | all green |

Four guards mutation-checked: unknown-variable rejection, the WhatsApp blocker
report, `NOT_APPLICABLE` for text channels, and purpose coverage.

## 18. Production verification

*(completed after deployment — see §18 in the released version)*

## 19. Financial safety

Nothing here writes anything. The registry is a read over a Python tuple and a
settings dict. Asserted on SQLite and again on PostgreSQL: settlement, invoice,
payment, receipt, customer-payment counts and settlement net and receivables
are snapshotted around repeated registry reads and required identical.

## 20. REAL versus TEST

**REAL** — the registry, purposes, variable validation (including the
now-rejected unknown variable), ordering, the WhatsApp readiness assessment,
provider-mapping status, the portal panel, RLS and the PostgreSQL proof.

**TEST** — nothing was sent. `messaging_mode` remains `test` on the deployment
and every provider is `disabled`.

**NOT DONE, deliberately** — no vendor selected, no account, no credential, no
contact, no purchase, and **no SMS, WhatsApp or email delivered to anybody**.

## 21. Known limitations

* No vendor, so no real message. Unchanged from DEMO-031.
* **All 8 business WhatsApp templates are not approvable as-is** (§11). This is
  the largest single blocker to real WhatsApp messaging and it needs a product
  decision, not code.
* The registry is read-only. Retiring or versioning a wording means shipping a
  release — which is the intent, and would become painful at a much larger
  template count.
* `version` and `active` are metadata that nothing yet branches on; no template
  is inactive and none has a second version.
* `notification_vendor_templates` is process-wide, so two tenants cannot have
  different approved templates for the same message.
* The DLT/sender-ID registration itself is not modelled: the registry knows a
  vendor template name, not a regulator's template id or approval state.
* Every regulatory claim above needs confirmation before anything is filed.

## 22. What must happen before production messaging

1. **Resolve the optional-segment conflict** (§11) — a product decision.
2. **Commercial evaluation** of the shortlist, confirming §8's seven unknowns.
3. **Contract** with a provider per market.
4. **Register**: DLT principal entity, header and content templates for India;
   sender ID for Kenya.
5. **Submit WhatsApp templates** for approval, per market and language, and
   record the approved names in `LACTEVA_NOTIFICATION_VENDOR_TEMPLATES`.
6. **Adapter**, if the vendor's API does not match Lacteva's documented HTTP
   contract.
7. **`LACTEVA_MESSAGING_MODE=sandbox`** and an executed run against the
   vendor's sandbox, including a real delivery receipt arriving.
8. **`production`**, deliberately, with a small pilot audience.

Steps 1–5 are commercial and regulatory. The engineering left is steps 6–8.

## 23. Recommended DEMO-033

**Recommended: resolve §11 and model template approval state.** The optional-
segment conflict is the one blocker that is Lacteva's to fix, and the registry
currently knows whether a vendor *name* is configured but not whether a
template is *approved*, *pending* or *rejected* — which is the thing an
operator will actually be tracking through steps 4 and 5 above. Both are small,
both are provider-neutral, and both are needed before a vendor exists.

**Not recommended yet:** the adapter itself, per-tenant template mapping, or
anything requiring a credential. All three depend on a commercial decision that
has not been made.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-032: an unknown template variable is no longer silently ignored, a provider-independent registry says what Lacteva sends and what a vendor would still need, and it surfaced that all 8 business WhatsApp templates are currently unapprovable. No vendor selected, contacted or credentialed. |
