---
id: DEMO-029-FINAL
title: DEMO-029 — Message Delivery Receipts & Recipient Reachability
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-028-FINAL, DEMO-027-FINAL, DEMO-025-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-029 — Message Delivery Receipts & Recipient Reachability

Two questions the platform could not answer: **did it arrive?** and **could it
ever have?**

---

## 1. What already existed

| Capability | State before DEMO-029 |
|---|---|
| Notification records, dispatch service, provider registry | complete (DEMO-025) |
| SMS / WhatsApp / email / push adapters, templates, tenant channel choice | complete |
| Recipient directory (`NotificationRecipient`) | complete |
| `provider_status`, `source_type` / `source_id` | complete (DEMO-028) |
| Idempotency, retry, RLS, business dates on both journeys | complete |
| **Signature-verified webhook boundary** | complete (DEMO-027) |

**The DEMO-027 boundary was reusable but not yet shared.** Its HMAC
construction and constant-time comparison lived *inside*
`TestPaymentProvider.parse_webhook`. Reusing it properly meant extracting the
mechanism, not copying it — see §4.

**Contact data needed no new home.** `SupplierProfile.phone`, `Customer.phone`,
`NotificationRecipient.{phone,email}`, and the dispatch service's own
`_CHANNEL_CONTACT` map already hold everything reachability needs. Nothing
anywhere knows WhatsApp capability, and no external lookup exists.

## 2. What was genuinely missing

1. **A message could never become `delivered`.** DEMO-028 stopped the portal
   *calling* acceptance delivery; it did not give the platform a way to learn
   the real thing.
2. **No way for a gateway to tell us.** No receipt endpoint existed.
3. **One signature mechanism, two would-be users.**
4. **No way to ask who cannot be reached** before a settlement run — the gap
   DEMO-028 recommended closing.

## 3. Delivery receipt architecture

```
gateway
   │  signed delivery report
   ▼
POST /v1/notifications/receipts/{provider}     unauthenticated by design
   │  verify   → core/webhook_security (ONE mechanism, shared with payments)
   │  claim    → notification_receipt_event, UNIQUE (provider, event_id)
   │  find     → notification by provider_reference — never from the payload
   │  apply    → forwards only; delivered is terminal
   ▼
notification.status = delivered | failed        LACTEVA's word
notification.provider_status = <gateway's own>  the GATEWAY's word
notification.delivered_at
```

**Statuses reuse the existing vocabulary rather than replacing it**:
`pending` is QUEUED, `sent` is SENT, `failed`/`dead` are FAILED. Only
`delivered` is new, and it is reachable **only** from a signature-verified
receipt — the same rule DEMO-027 applied to `past_due`.

**There is no `read` status.** No gateway this platform speaks to reports one,
and §2 forbids inventing provider capabilities.

## 4. Provider webhook

**One mechanism, extracted rather than duplicated.** `core/webhook_security`
now holds `sign`, `compare`, `verify` and `header_value`; the payment adapter
imports what it used to inline, and the receipt adapter imports the same
thing. Nothing about the payment path changed — its 45 tests passed unmodified
against the extracted version — and a test fails if a second `hmac.new` or
`compare_digest` ever appears in any `webhooks.py`, `receipts.py` or module
`providers.py`.

The four refusals are the payment webhook's four:

* **Never a tenant from the payload.** The tenant comes from the `notification`
  the provider reference names.
* **Never a notification created.** An unknown reference writes nothing, so an
  unauthenticated endpoint cannot fill a table.
* **Never twice.** `(provider, event_id)` is unique.
* **Never backwards.** See §5.

It returns **200** for a replay, an unknown reference, and a report that
deliberately changed nothing — a gateway reads non-2xx as "retry". **401** and
**404** never say which check refused.

**Receipts are optional per provider.** `ReceiptCapableProvider` is structural:
a provider without `parse_receipt` has no endpoint and the route answers 404.
Most gateways send delivery reports; assuming they all do would be inventing
capability.

## 5. Status model

| current | reported | result |
|---|---|---|
| `sent` | delivered | **delivered** |
| `sent` | failed | **failed** |
| `sent` | unknown | ignored |
| `failed` | delivered | **delivered** — a gateway that failed then delivered told us something later |
| `delivered` | *anything* | **ignored** — terminal |
| `pending` / `dead` | anything | ignored — nothing was ever handed over |

`delivered → sent` is impossible, as §4 requires. A vendor's spelling
(`DELIVRD`, `success`, `undelivered`, `expired`) is normalised **in the
adapter**, so the domain never grows a table of gateway synonyms; anything
unrecognised is `unknown` and moves nothing.

**A defect found by mutation testing, in my own code.** The first draft had
both a terminal-`delivered` check *and* a `_RECEIVABLE` tuple that also
excluded `delivered`. Disabling the terminal check failed **no test** — it was
dead code that looked load-bearing, and a future editor "simplifying" the
tuple would have silently removed a protection they believed was elsewhere.
Restructured so each rule carries its own weight: mutating either now fails
tests (4 and 2 respectively).

## 6. Idempotency

`(provider, event_id)` unique, claimed inside a savepoint with the `add`
**inside** it — the DEMO-025 lesson. Never `SELECT`-then-`INSERT`. Proven on
real PostgreSQL: eight concurrent deliveries of one receipt yield exactly one
`delivered` and seven `replayed`, one ledger row, one delivery timestamp.

## 7. Recipient reachability

**A derivation, not a directory.** Nothing is stored; it reads what the
platform already keeps, through the same directory a send reads, so the report
cannot describe a channel or an address the message would not have used.

| Answer | Meaning |
|---|---|
| `reachable` | there is an address of the kind this channel needs |
| `unreachable` | there is not — `phone_missing`, `invalid_phone`, `email_missing` |
| `unknown` | the platform cannot tell — `whatsapp_unknown`, `provider_unavailable`, `no_supported_channel` |

**WhatsApp is never `reachable`.** A phone number is not a WhatsApp account,
nothing here can ask a gateway, and reporting otherwise would invent a
capability. The same number *is* reachable by SMS, which is the whole point of
the distinction.

**A disabled channel blames the deployment, not the farmers.**
`provider_unavailable` is `unknown`, never `unreachable` — listing 250
blameless farmers as unreachable would bury the one fact an operator needs.

The phone check is deliberately **permissive**: it can say "certainly not a
number" and never "this number works". A false *invalid* accuses a record of
being wrong and sends someone to fix what is fine; a false *valid* simply lets
the send fail visibly in the history, where failure is already handled.

Contacts are **masked** in the report by the existing convention — an operator
sees which number is on file without the report becoming a list of farmers'
phone numbers.

## 8. Settlement communication

```
250 farmers → 223 reachable · 17 unreachable · 10 unknown
              9 phone missing · 5 invalid phone · 3 provider unavailable
```

**Nobody is silently skipped**: every non-reachable recipient is named, and
when the list is capped the response says so rather than letting a long list
look short.

**It blocks nothing.** A farmer with no phone number is settled, finalized and
owed exactly the same amount — asserted by a test that strips a farmer's phone
number *before* finalizing and requires the settlement to succeed. Money and
communication are separate domains.

## 9. Invoice communication

The same service, the same endpoint, the same code — `subject_type=customer`
reads `Customer.phone` instead of the supplier directory, because that is where
a household's number lives and where the invoice event already reads it from.
No duplicate implementation.

Households have **no email anywhere in this platform**, so on an email channel
they report `email_missing` — which is true, and better than inventing a column
nobody collects into.

## 10. Security and RLS

`notification_receipt_event` is tenant-owned, derived into the protected set
from model metadata, RLS enabled and **forced**, among **69 policies**. Proven
on PostgreSQL: a second tenant querying with no filter sees zero receipts,
cannot read the message text, and deletes zero rows.

| Attempt | Result |
|---|---|
| Reachability report, no token | **401** |
| Reachability report, another tenant | their own zero, never ours |
| Unsigned or wrongly-signed receipt | **401**, nothing written |
| Receipt for an unknown message | **200**, nothing written |
| Receipt for a provider without receipts | **404** |

The reachability service is constructed from the **authenticated principal's**
tenant — one dairy cannot ask who is unreachable at another, because the answer
is a list of that dairy's farmers.

## 11. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — **PASSED**, head `f3a9c71d5e28`, **153 tests
in step 3** (up from 136), 0 skipped, 69 policies.

`tests/test_delivery_receipts_postgres.py` is in the proof's explicit file list
and covers all sixteen properties §21 names: valid receipt, duplicate,
**concurrent** duplicate, invalid signature, replayed event, unknown message,
out-of-order events both ways, transition safety, cross-tenant isolation,
reachability counting, missing phone, invalid phone, disabled channel, unknown
WhatsApp capability, and that neither settlement nor invoice communication
moves a financial total.

## 12. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **1885 passed**, exit 0 |
| `tests/test_delivery_receipts.py` (new) | 48 |
| `tests/test_delivery_receipts_postgres.py` (new) | 17, on real PostgreSQL |
| Admin portal (`vitest`) | **269 passed** (20 files) |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |
| Lint, format, tsc, eslint, build, docs, xref | all green |

Four guards mutation-checked: the terminal-`delivered` rule, the `_NEVER_SENT`
rule, the replay ledger, the WhatsApp-unknown rule, and the shared signature
verification — each making tests fail, and one of them exposing the redundancy
described in §5.

## 13. Production verification

*(completed after deployment — see §13 in the released version)*

## 14. REAL versus TEST

**REAL**
* The receipt boundary, signature verification, replay ledger, transition
  rules, provider-name resolution, and the `delivered` status.
* `HttpSmsProvider` (and its WhatsApp subclass) parse Lacteva's **documented**
  delivery-report contract — the same idea as its documented send contract, and
  deliberately Lacteva's rather than any named vendor's.
* Reachability for both journeys, end to end.

**TEST / DEMO**
* `ReceiptTestProvider` — extends `LoggingProvider`, sends nothing anywhere,
  cannot be selected by configuration, installed only by a test.
* Every receipt in every test is one of these. **No external message was sent
  and no real gateway was contacted.**

**NOT IMPLEMENTED**
* **No production messaging provider is enabled**, and none was enabled here.
  No credentials were created.
* No `read` receipts — no gateway reports them.
* No WhatsApp capability lookup — hence `unknown`, permanently, until a
  provider that can answer is contracted.
* No per-recipient contact editing from the report; it identifies, it does not
  repair.

## 15. Financial safety

A delivery receipt is a communication event. `receipts.py` and
`reachability.py` import neither `modules.settlement` nor `modules.payment`,
asserted by a test, and the PostgreSQL proof snapshots settlement, invoice,
payment, receipt and customer-payment counts plus settlement net and
receivables around a full receipt cycle for **both** journeys and requires them
identical.

## 16. Known limitations

* Nothing is delivered in production and nothing claims to be; every channel on
  the live deployment remains `disabled`.
* `delivered` is unreachable in production until a gateway is contracted and a
  receipt secret configured.
* The phone check is syntactic. A well-formed number that nobody answers reads
  as `reachable` until a send fails.
* Reachability evaluates the tenant's *whole* directory, not the specific
  recipients of one settlement batch — the batch does not exist as an entity
  yet.
* No per-recipient preferred channel: tenants choose per template, not per
  person.
* Email reachability for households is always `email_missing`, because no
  household email is collected anywhere.
* Receipt events accumulate; nothing prunes them yet.

## 17. Recommended DEMO-030

**Recommended: close the loop the report opens — contact repair and a
settlement-scoped batch.** This milestone can tell an operator that 17 farmers
have no usable number; it cannot help them fix it, and it evaluates every
farmer rather than the ones in the run about to happen. Both are small,
concrete, and needed before either is genuinely useful: a supplier contact
edit path with audit, and a reachability report scoped to the settlements in a
period.

**Then: the first contracted gateway.** Everything above the vendor line is
built and executed — send, receipt, replay, transitions, reachability. What
remains is one adapter, one credential in deployment configuration, one webhook
URL registered, and a run against the vendor's sandbox. By the standing rule
here, none of this milestone is evidence that a particular vendor behaves as
documented until that has been executed.

**Not recommended yet:** notification preferences, quiet hours, or per-recipient
opt-out. All three are only meaningful once real messages are being delivered.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-029: a message can finally become DELIVERED — only from a signed provider receipt, once, and never backwards — and an operator can see who could never have been reached, without that blocking a single farmer's settlement. |
