---
id: DEMO-005-FINAL
title: DEMO-005 — Guided Collection Capture Workflow
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-12
last-updated: 2026-08-12
related: [DEMO-004-FINAL, DEMO-003-FINAL, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-005 — Guided Collection Capture

**Work order:** DEMO-005
**Deployed to:** https://dev.phoenixsoft.in — release `demo005-f528dfe`
**Status:** COMPLETE

---

## 1. The existing state machine, as found

Documented from `modules/milk_collection/service.py` before any UI was written.

| # | Endpoint | From state | To state |
| --- | --- | --- | --- |
| — | `POST /v1/collection-sessions` | — | an open session at a **ready** centre; a centre permits only **one** |
| 1 | `POST /v1/milk-transactions` `{session_id}` | — | `NEW` |
| 2 | `POST /{id}/identify` | `NEW` | `SUPPLIER_IDENTIFIED` |
| 3 | `POST /{id}/milk` | `SUPPLIER_IDENTIFIED` | `MILK_RECEIVED` |
| 4 | `POST /{id}/weight` | `MILK_RECEIVED` | `WEIGHT_CAPTURED` → **`QUALITY_PENDING`** (the platform hands off by itself) |
| 5 | `POST /{id}/quality` | `QUALITY_PENDING` | `QUALITY_CAPTURED` → `PRICING_PENDING` → `PRICED` |
| 6 | `POST /{id}/accept` | `PRICED` | `ACCEPTED` |
| 6b | `POST /{id}/reject` `{reason}` | `PRICED` | `REJECTED` |
| 7 | `POST /{id}/complete` | `ACCEPTED` \| `REJECTED` | `COMPLETED` |
| — | `POST /{id}/cancel` | any open state | `CANCELLED` |
| — | `GET /{id}/events` | — | the nine-event trail |

**Validation the domain enforces** (all verified live, §8):
`_get_mutable(expected=…)` refuses any out-of-order step and names the state it
wanted; a centre must be READY to open a session; a supplier must be `active`;
`milk_type ∈ (cow, buffalo, goat, mixed, custom)`; weight must be `kg`, manual
requires gross **and** tare, `gross > 0`, `tare < gross`, `gross ≤ 200`;
quality manual requires fat, SNF and CLR, each inside `QUALITY_RANGES`
(fat/SNF 0–15, CLR 20–40); `mock_scale` and `mock_analyzer` are **refused**
unless `mock_hardware_enabled`, which is false in production.

**No endpoint was invented, no state skipped, and no second workflow created.**

## 2. The guided workflow

`/transactions/new`. The design decision that shapes the whole file:

> **The backend is the state machine.** The wizard has none of its own — the
> step it shows is *derived* from `transaction.state`, which the platform sets.
> Every button is one real call to one real endpoint, and the answer decides
> what happens next.

A front-end state machine would be a second source of truth, and the two would
eventually disagree in front of a customer. Deriving the step also makes
refresh trivially correct: the id is kept in `sessionStorage`, the transaction
is re-read, and the wizard resumes where the **platform** says it is — not
where the browser last thought it was. A collection the platform has already
completed is dropped from storage rather than resumed.

Stepper states are Completed / Current / Pending, with the current step marked
`aria-current="step"`.

## 3. Centre and supplier validation

**Centre** — the operator picks one, and the wizard calls the real
`/readiness` endpoint. Every check is listed with the platform's own reason for
each failure, and **"Start collection" stays disabled** until the platform says
the centre can receive milk. Readiness is never inferred from a centre record
existing.

**Supplier** — only `active` suppliers are offered, and when the platform
refuses anyway its sentence is shown verbatim (`supplier is draft, not active`).
The rule is not re-implemented in the browser; it is obeyed.

**Session** — the wizard joins the centre's open session if there is one and
opens a new one otherwise. A centre permits only one, and taking over another
operator's shift is not this screen's business.

## 4. Product, weight and quality capture

Milk type and container from the domain's own vocabulary. Weight and quality
are entered by hand and sent with **`source: "manual"`**, which is the domain's
own name for an operator reading — both screens are labelled *"Manual demo
capture"* with a pen icon, and the weight card says explicitly that the value
was entered by an operator, not read from a scale.

**Nothing pretends to be hardware.** `mock_scale`/`mock_analyzer` are never
sent; a portal test asserts the weight body contains no `mock` anywhere; and
the platform refuses them in production regardless (§8, failure 5).

Client validation mirrors the domain bounds to give a fast, specific message —
never to decide what is allowed. Net weight is computed by the platform, and
the form says so.

## 5. Pricing resolution

Recording quality is what asks the pricing engine for a rate. The review screen
then **prints** the result:

```
10 × 45.5000
= 455.00 KES
```

Those are three separate values the platform returned, placed side by side. The
portal does not evaluate the expression — the same rule DEMO-004 established,
and for the same reason: multiplying in React would be a second pricing engine.
The rate card and band (`RC-2026-MAIN v1 band [4.0, 5.0)`) are shown alongside,
so an operator can see *why* that rate applied.

## 6. Acceptance and completion

Acceptance requires an **explicit confirmation** naming the amount that becomes
payable — never automatic. Acceptance and completion are separate buttons
because they are separate decisions in the domain, and a rejected collection
still has to be completed to close the paperwork.

The success screen shows the collection id, supplier, centre, quantity, rate,
value, status and timestamp — then says plainly what has **not** happened:

> ○ Settlement — this collection becomes payable when a settlement period
> collects it · ○ Payment · ○ Receipt
>
> Collection completion is not settlement, and settlement is not payment.

## 7. Event timeline

The DEMO-004 timeline is reused unchanged: the nine real events from
`/events`, then the four money stages from the chain aggregate, drawn as
**pending until they have actually happened**. Verified live: the demonstration
collection's chain returns `settlement: null, payment: null, receipt: null`
immediately after completion — which is the truth, and the point.

## 8. Error and recovery handling

Every refusal below was produced **live on the deployed platform**, and the
wizard shows the platform's `extra` (the business reason) rather than the
generic RFC-9457 `detail`:

| Provoked failure | What the platform said |
| --- | --- |
| Repeat a step on a finished collection | `transaction is COMPLETED and immutable` |
| Weight before milk | `expected state MILK_RECEIVED, transaction is NEW` |
| Tare heavier than gross | `tare must be less than gross` |
| Fat outside plausible range | `fat out of range [0.0, 15.0]` |
| **Mock hardware in production** | `mock_analyzer is not permitted in this environment — capture a real reading` |

Recovery: after any refusal the wizard **re-reads the transaction**, because a
rejection may mean the platform moved on without us (a duplicate submit, another
operator) and guessing would be worse than asking. State-changing calls are
never retried blindly. Refresh and re-entry resume from the platform's state.

## 9. The demonstration scenario

Reproducible, and taken from the deterministic demo data — nothing hard-coded
in the application.

| | |
| --- | --- |
| Centre | Kilima Hill Collection Centre (`KH-C1`) |
| Supplier | Amina Njoroge |
| Milk / container | cow, can |
| Gross / tare | 12.000 kg / 2.000 kg |
| Quality | fat **4.4**, SNF 8.6, CLR 28.5 |
| Band resolved | `RC-2026-MAIN v1 band [4.0, 5.0)` |
| Rate | **45.5000 KES/kg** |
| **Value** | **455.00 KES** |

Live collection created by this run: `213ba017-c39f-4f74-b3c9-2046239d1d60`.

## 10. Financial reconciliation

Verified through the deployed API **and** independently in PostgreSQL:

```
state | net_weight | unit_price | gross_amount | currency | weight_source | quality_source
COMPLETED | 10 | 45.5000 | 455.00 | KES | manual | manual
```

Independent arithmetic: **10.0 × 45.5000 = 455.00000**, matching the backend's
`455.00` exactly. `weight_source` and `quality_source` are both `manual` — the
database itself records that no device supplied these readings.

The chain immediately after completion is empty, confirming that completion is
a distinct stage from settlement and payment.

## 11. Tenant isolation

Verified live against the capture endpoints, signed in to the other demo
organization:

| Attempt | Result |
| --- | --- |
| Read another org's collection | **404** |
| Drive another org's collection (`/accept`) | **404** |
| Create a transaction in another org's session | **404** |
| See its own centres | 1 (its own only) |

Backed by a backend test that asserts the same three refusals. Never 403 —
another organization's records do not announce their existence.

## 12. Tests

| Suite | Result |
| --- | --- |
| Backend (`pytest tests/`) | **1,141 passed, 74 skipped, 0 failed** (was 1,134; **+7**) |
| Portal (`vitest`) | **121 passed** (was 111; **+10**) |
| Portal typecheck | clean |
| Portal lint (`--max-warnings 0`) | clean |
| Portal production build | succeeds — `/transactions/new` present |
| Backend lint + format | clean |

**Backend**: the full capture sequence through every real state, ending priced,
accepted and completed at 450.00; an out-of-order step refused with the state it
expected; a repeated step refused rather than duplicated; weight bounds; quality
range; manual capture recorded as manual; another tenant unable to read, drive
or create.

**Portal**: a not-ready centre blocks the start and shows the reason; a ready
one enables it; **the wizard drives the real endpoints in order** (asserted as
the exact POST sequence); measurements are sent as `manual` with no `mock`
anywhere; weight validated before troubling the platform; the platform's
business reason surfaced on refusal; the price **printed** and acceptance
confirmed explicitly; refresh resumes from the platform's state; a completed
collection is forgotten.

Two flaws in my own tests, both fixed rather than worked around:

- The mock matcher used `includes("/milk")`, which also matches
  `/milk-transactions/tx-1/weight` — it silently answered the wrong step.
- The date tests used `date.today()` (local) while the platform stamps UTC.
  They passed for hours, then failed the moment the local clock crossed
  midnight ahead of UTC. All date assertions now use `utcnow()`. This is the
  same trap PILOT-F03 recorded, met again.

One test I wrote asserted that mock hardware is refused — but mocks are
deliberately **enabled** in the test environment and refused in production, so
the assertion was wrong. It was replaced with one that checks what the wizard
actually relies on; the refusal itself is proven by the pre-existing
`test_mock_hardware_boundary.py` and demonstrated live in §8.

## 13. Live browser verification

All against https://dev.phoenixsoft.in after deploying `demo005-f528dfe`.

| Step | Result |
| --- | --- |
| Login (demo manager) | 204 |
| `/transactions` and `/transactions/new` | 200 |
| Centre readiness | `WARNING`, 2 of 6 checks failing — shown with reasons |
| Session | joined the centre's existing open session |
| Create → identify → milk → weight → quality | `NEW` → `SUPPLIER_IDENTIFIED` → `MILK_RECEIVED` → `QUALITY_PENDING` → `PRICED` |
| Pricing | 10.0 kg × 45.5000 = 455.00 KES, band `[4.0, 5.0)` |
| Accept → complete | `ACCEPTED` → `COMPLETED` |
| Event trail | 9 real events |
| Chain after completion | all null — completion is not payment |
| Collection detail page | 200 |
| Validation failures | five, each with its real business reason (§8) |
| Tenant isolation | 404 on read, drive and create |

## 14. AWS impact

| | |
| --- | --- |
| AWS resources created | **0** |
| AWS resources resized | **0** |
| AWS managed services added | **0** |
| Terraform infrastructure changes | **0** |
| EC2 / EBS / EIP / DNS | unchanged |

PostgreSQL, Redis and RabbitMQ remain in Docker Compose on the existing EC2.

**Data safety:** no organization, collection, settlement, payment or receipt
was deleted, and the database was not reseeded. This work order added exactly
**two** collections to the demo organization — one completed demonstration and
one probe used for the validation failures, which was **cancelled** through the
domain's own `cancel` operation rather than deleted.

## 15. Known limitations

1. **Repeating the demo adds a collection each time.** The domain has no
   idempotency key on collection creation, and inventing one would have been a
   business rule. Each run is a genuine collection; the counts move. Cancelling
   is the domain's way to discard one, which is what the probe used.
2. **Rejection is reachable but not surfaced as a button.** `POST /{id}/reject`
   exists and the wizard renders a rejected collection correctly, but the
   review screen offers only Accept. A "Reject" action with a reason field is a
   small addition and belongs with a quality-failure demonstration.
3. **`container_type` and milk types are a fixed list in the UI.** They match
   the domain's `MILK_TYPES` constant, but there is no endpoint to enumerate
   them, so the list is duplicated in the portal and would drift if the domain
   grew a type.
4. **`sessionStorage`, not a URL.** An in-progress collection is not shareable
   or resumable in another tab. A `?transaction=` parameter would fix that.
5. **No optimistic UI.** Each step waits for the platform. That is deliberate —
   the platform decides the next state — but it does mean a visible pause per
   step on a slow link.
6. **The demonstration centre reports `WARNING`.** Two non-blocking readiness
   checks fail on the seeded centre, so the demo shows a warning rather than a
   clean `READY`. It is honest, but a spotless centre would demo better.

## 16. Recommended DEMO-006

**DEMO-006 — Settlement and payment operations.**

The story now runs from an empty screen to a completed, priced collection, and
DEMO-004 shows where that money goes. The gap is the middle: **the operator
actions that turn collections into money** are still only reachable through the
API.

1. **Settlement detail page** (`/settlements/{id}`) with its lines, totals and
   the collect → calculate → finalize lifecycle, obeying BR-0010's immutability
   and BR-0027's carry-forward — both already implemented and both invisible.
2. **Payment detail page** and the draft → pending → processing → completed
   lifecycle, including the failure path, since failed payments are already a
   dashboard attention item with nowhere to go.
3. **Link the DEMO-004 chain cards** to those pages, closing the last dead-end
   in the navigation (limitation 3 of DEMO-004).
4. Consider the **rejection action** from limitation 2 above, which pairs
   naturally with showing a settlement refusing an unpriced collection.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-12 | Platform Engineering | DEMO-005: guided capture driving the real seven-step collection state machine, with the step derived from the platform's own state; readiness-gated centre selection; manual-only measurement capture; printed pricing; explicit acceptance; refresh-safe resume; deployed as `demo005-f528dfe`. |
