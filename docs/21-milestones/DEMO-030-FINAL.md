---
id: DEMO-030-FINAL
title: DEMO-030 — Contact Repair & Settlement-Period Reachability
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-16
last-updated: 2026-08-16
related: [DEMO-029-FINAL, DEMO-028-FINAL, DEMO-025-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-030 — Contact Repair & Settlement-Period Reachability

DEMO-029 could tell an operator that seventeen farmers were unreachable. This
milestone is about what happened when they went and fixed one: **nothing.**

---

## 1. What already existed

| Capability | State before DEMO-030 |
|---|---|
| `SupplierProfile.phone`, `Customer.phone`, the notification directory | complete |
| `PUT /v1/suppliers/{id}` → `SupplierService.update_profile` | existed |
| Audit infrastructure (`AuditService.record`, free-form `detail`) | complete |
| Reachability derivation, three-answer vocabulary, masking | complete (DEMO-029) |
| Delivery receipts, provider boundary, RLS, business dates | complete |
| Mobile supplier edit screen (phone field, `PUT /v1/suppliers/{id}`) | complete |

## 2. What was missing — and the defect

**Repairing a farmer's phone number did nothing that mattered.**

```python
async def update_profile(...):
    profile.phone = cmd.phone      # updates supplier_profile
    await self._audit.record(...)  # with NO detail: no before, no after
    return profile                 # and publishes NOTHING
```

The notification directory is built **only** from `supplier-registered` and
`supplier-status-changed`. `create` publishes contact fields with an explicit
comment — *"Contact details for the notification recipient directory (NOT-001)
— consumers must never query this module"* — and an update published nothing at
all.

So `supplier_profile.phone` changed and `notification_recipient.phone` did not.
The reachability report still showed the farmer unreachable, and
`_resolve_recipient` — which reads the directory — would still have sent the
next settlement message to the old number. An operator could act on DEMO-029's
report, see no change, and reasonably conclude the report was broken.

Three smaller gaps: the audit recorded no before or after, no phone validation
existed anywhere in the platform, and reachability evaluated the whole
directory rather than the farmers in the run about to happen.

## 3. Contact repair

`PATCH /v1/suppliers/{supplier_id}/contact` — phone, optional locale, optional
reason.

**A PATCH rather than the existing PUT, deliberately.** An operator acting on a
reachability report is fixing one thing; making them resend the whole profile
is how a forgotten field silently blanks a `national_id` or a `village`. The
full-profile PUT still works and is **also fixed** — both paths now audit
properly and publish, because the fix belongs in the service rather than in one
endpoint.

Behind the existing `supplier.manage` permission. A narrower one would have
meant a role that can change a farmer's phone number but not their name.

**No second contact directory.** There is one supplier contact record, one
notification directory, and now one event connecting them — asserted by a test
that scans every module for a table whose name suggests otherwise.

## 4. Audit trail

Every repair records who, when, what changed, from what, to what, and why:

```json
{"changed": ["phone"],
 "phone": {"from": "07•••••678", "to": "+91•••••199"},
 "reason": "farmer changed number"}
```

**The number is masked**, by the same convention the notification history uses.
An audit log is read far more widely than a contact record; an operator needs
to verify that a repair happened, not to have the log become a directory of
farmers' phone numbers. A test asserts the full number never appears.

A repair that changes nothing writes the audit entry and **publishes no
event** — a no-op must not appear in the directory's history as a repair.

## 5. Settlement-period reachability

Same engine, different question:

```
Period 2026-08-01 → 2026-08-31
Recipients: 250 · Reachable 223 · Unreachable 17 · Unknown 10
  9 phone missing · 5 invalid phone · 3 not in directory
```

`for_subjects(subject_ids)` evaluates a **named set** rather than the whole
directory. `evaluate` still decides, `_summarise` still counts, and the
vocabulary is DEMO-029's — one derivation, asked two ways.

**A supplier with a settlement and no directory entry is reported**, as
`not_in_directory`, rather than omitted. Being absent from the contact
directory is exactly the kind of unreachable that a report listing only known
contacts would hide.

**Overlapping, not contained**: a settlement running 1–31 August answers a
question about 1–15 August. An operator asking about a fortnight must not be
told about nobody because settlements happen to be monthly.

### A boundary violation, caught by an earlier milestone's test

The first draft imported `Settlement` into the notification module and queried
it there. `test_the_receipt_path_never_imports_the_financial_modules` — written
in DEMO-029 for a different reason — failed, and it was right: *"never query
another module's tables, never import its models."*

Corrected by composition, which is what the platform already does everywhere
else: `SettlementService.supplier_ids_in_period()` answers **who is being
settled** (ids only; nothing about money leaves), `ReachabilityService.for_subjects()`
answers **whether they can be reached**, and the route composes them. A new
test now pins the boundary from the notification side as well.

## 6. Business-date handling

The period defaults on the **organization's** calendar, via
`tenant_timezone(session)` and `business_today` — the same machinery the
calendar and the scheduler use. `date.today()` here would silently give an
Indian dairy the previous month for five and a half hours every night, and a
Kenyan one for three.

An inverted period is refused rather than silently returning nothing.

## 7. Settlement safety

**Reachability blocks nothing, ever.** A test strips a farmer's phone number
*before* finalizing and requires the settlement to succeed with its amount
intact; the PostgreSQL proof asserts an unreachable farmer still holds a
finalized settlement of the same value. Communication status is not a financial
input, and money and communication remain separate domains.

## 8. Portal changes

The existing notifications page, extended — **no new page, no new component**.
The reachability panel gains two date inputs (empty means the DEMO-029
directory-wide report; filled scopes it to the settlement period), a **Repair**
button on each affected supplier row, and a small inline form: phone, reason,
save. It reuses the page's own `Select`, `Input`, `Button` and `StatCard`.

The form says plainly that a valid number means the contact is usable, **not
that WhatsApp will reach it** — DEMO-029's distinction, kept where an operator
will actually read it.

## 9. Mobile

**Unchanged, and it did not need to change.** The mobile app already has a
supplier edit screen with a phone field, and it calls `PUT /v1/suppliers/{id}`
— the path this milestone fixed. A number corrected on a phone in a collection
centre now reaches the directory and is audited with before and after, with no
mobile code touched. That is the fix being at the right layer rather than in an
endpoint.

## 10. Security and RLS

| Attempt | Result |
|---|---|
| Repair with no token | **401** |
| Repair as `tenant-viewer` | **403** |
| Repair another tenant's supplier | **404** — never 403 |
| Read another tenant's contact under RLS | zero rows |
| Read another tenant's repair audit trail | zero rows |
| Period report for another tenant | their own zero |

The reachability service is constructed from the authenticated principal's
tenant; there is no parameter that could point it elsewhere.

## 11. PostgreSQL proof

`./infra/ci/verify-postgres.sh` — **PASSED**, **167 tests in step 3** (up from
153), 0 skipped, 69 policies.

`tests/test_contact_repair_postgres.py` is in the proof's explicit file list and
covers all thirteen properties §12 names, including: **concurrent repairs**
(four operators fixing one farmer at once must leave one coherent contact in
both the profile and the directory, never a mixture), **concurrent reachability
calculations** (six simultaneous reports must agree), a repaired recipient
becoming reachable, and settlement and financial records unchanged throughout.

## 12. Tests

| Suite | Result |
|---|---|
| Backend (`pytest tests/`) | **1927 passed**, exit 0 |
| `tests/test_contact_repair.py` (new) | 29 |
| `tests/test_contact_repair_postgres.py` (new) | 14, on real PostgreSQL |
| Admin portal (`vitest`) | **273 passed** (20 files) |
| Mobile `flutter analyze` / `flutter test` | no issues / **125 passed** |
| Lint, format, tsc, eslint, build, docs, xref | all green |

**Mutation-checked.** Reproducing the original defect — publishing an event the
directory does not listen for — fails exactly the three tests about it and
nothing else. Making the directory coalesce instead of assign fails 2; removing
phone validation fails 5; ignoring the period scope fails 2.

**A pre-existing test fixture was corrected, not the guard.**
`test_import_mixed_results` used `"+254711"` — six digits, which is not a Kenyan
number or anyone's. The row's purpose is to be the one that succeeds, so it now
carries a number that could exist.

## 13. Production verification

Deployed `main-b337b5e` to **https://dev.phoenixsoft.in** through the existing
path. **No migration was required and none ran** — the schema stayed at
`f3a9c71d5e28` and the deploy printed no "the schema moved" notice, which is
§14's explicit ask answered by the deployment itself rather than by assertion.

All nine components healthy, 11 containers healthy, dead-letter queue 0,
undelivered outbox 0, scheduler intact (12 generation runs). RLS still enabled
and **forced** on `supplier_profile`, `notification_recipient` and
`audit_record`, among 69 policies.

**The defect, fixed and proven on production.** A round-trip on one demo
supplier:

| Step | Result |
|---|---|
| `PATCH …/contact` to a new number | **200**, profile updated |
| `notification_recipient.phone` seconds later | **updated** — this is the thing that used to never happen |
| `PATCH …/contact` with `"call the office"` | **422**, nothing changed |
| `PATCH …/contact` restoring the original | **200**, profile and directory both back |

Net data change: **zero** — the original number is restored in both tables.
What remains is two append-only audit entries, which is exactly what should
remain:

```
{"changed": ["phone"], "phone": {"from": "+2547****0000", "to": "+2547****0111"},
 "reason": "DEMO-030 production verification"}
{"changed": ["phone"], "phone": {"from": "+2547****0111", "to": "+2547****0000"},
 "reason": "DEMO-030 verification: restoring original"}
```

Before, after, reason, and **masked** — the audit trail records that a number
changed without becoming a list of numbers.

**Settlement-period reachability on both tenants**, defaulted on each
organization's own calendar:

| Tenant | Channel | Total | Reachable | Unreachable | Unknown | Reason |
|---|---|---|---|---|---|---|
| India | sms | 12 | 0 | 0 | **12** | `provider_unavailable` |
| Kenya | sms | 24 | 0 | 0 | **24** | `provider_unavailable` |

Every provider is `disabled`, so the platform blames itself once rather than
accusing 36 blameless farmers — and names every one of them. Unauthenticated
calls to both the report and the repair endpoint return **401**.

**No external provider was contacted and no message was sent**: 0 delivered, 0
receipt events, 12 `sent` unchanged from before the deploy.

Month-to-date AWS cost effectively nil.

**The browser walkthrough was NOT performed** — the Chrome extension is not
connected in this session, so the repair form and the period inputs were
verified by their own tests and by the API, not visually. Same gap as the
previous four milestones, stated rather than papered over.

## 14. Financial safety

Nothing here writes to a financial table. Two tests hold it: one snapshots
settlement, invoice, payment, receipt and customer-payment counts plus
settlement net and receivables around repairs and reports and requires them
identical; the other asserts the notification module imports neither
`modules.settlement` nor `modules.payment`.

**Verified on production, before and after the deployment — including across
the contact-repair round-trip:**

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
| Supplier profiles / directory entries | 44 / 44 | **44 / 44** |

Every figure identical. A verified backup was taken first — 69 tables, 41,547
rows, `verified: true`, plus a second explicit verify pass — on top of the one
`deploy.sh` takes itself.

## 15. REAL versus TEST

**REAL** — contact repair, the audit trail, validation, reachability, the
settlement-period calculation, the event that carries a repair to the
directory, RLS, and the PostgreSQL proof.

**TEST** — external messaging. Every messaging provider on the deployment
remains `disabled`; no gateway was contacted and no credential created. **No
SMS or WhatsApp message was delivered by this milestone**, and nothing claims
one was.

## 16. Known limitations

* **No schema change was required, and none was made** (§14's explicit ask).
  Every fact already had a column.
* Only supplier contacts are repairable. Households have `Customer.phone` and
  no repair endpoint yet — the reachability report covers them, the fix does
  not.
* No per-supplier preferred channel: the model has no column for one, and §2
  hedges "where the existing model supports it". Tenants still choose per
  template.
* The phone check is syntactic and permissive. A well-formed number nobody
  answers reads as reachable until a send fails.
* Concurrent repairs resolve last-writer-wins. That is correct — both numbers
  came from a human — but nothing warns the loser.
* No bulk repair or CSV round-trip; one farmer at a time.
* Households still have no email anywhere, so email reachability for customers
  remains `email_missing`.

## 17. Recommended DEMO-031

**Recommended: the first contracted gateway.** Everything above the vendor line
is now built and executed — reachability, repair, send, receipt, replay,
transitions — and the remaining gap is one adapter, one credential in
deployment configuration, one webhook URL registered, and a run against the
vendor's sandbox. By the standing rule here, none of the last three milestones
is evidence that a particular vendor behaves as documented until that has been
run.

**Then: customer contact repair**, which is the same shape as this milestone
for households — and worth doing after a gateway, because until messages
actually go out, a household's phone number has never been tested against
anything.

**Not recommended yet:** bulk contact import/repair, per-recipient channel
preferences, or notification quiet hours. All three are only meaningful once
real messages are being delivered.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-16 | Platform Engineering | DEMO-030: repairing a farmer's phone number now actually reaches the directory a message is sent from — it did not — with before-and-after audit, validation, and a reachability report scoped to the farmers in the settlement run about to happen. No schema change. |
