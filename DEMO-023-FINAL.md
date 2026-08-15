---
id: DEMO-023-FINAL
title: DEMO-023 — Single Working-Day Resolution Path for Operations Readiness
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-022-FINAL, DEMO-021-FINAL, DEMO-020-FINAL, CON-0001]
baseline: ARCH-BASELINE-V1
---

# DEMO-023 — Single Working-Day Resolution Path for Operations Readiness

One inconsistency, closed. DEMO-022 routed the delivery scheduler through
`WorkingDayResolver` and left the readiness engine reading
`center_calendar_entry` itself. This milestone removes that second reader, and
**does nothing else** — no schema change, no new abstraction, no migration.

---

## 1. What already existed

| Piece | Where | Since |
|---|---|---|
| `resolve_working_day(organization, centre)` — the pure rule | `business_calendar` | DEMO-021 |
| `WorkingDayResolver` — the one path, cached per centre | `business_calendar` | DEMO-022 |
| `centre_exception_is_working(kind)` | `business_calendar` | DEMO-021 |
| Scheduler resolving through it | `delivery/scheduler.py` | DEMO-022 |
| Readiness reading the centre calendar **directly** | `operational_readiness` | DEMO-005 |

The survey found exactly one remaining production path that decided
working/non-working on its own: `ReadinessEngine._calendar_check`. Everything
else — the scheduler, the calendar API, the portal — already went through the
resolver or asked the server.

## 2. What DEMO-023 changed

**`_calendar_check` now asks `WorkingDayResolver`.** The centre's own entry is
still read, but only to *say why* — the decision is no longer made from it.

**`centre_calendar_kind` became `centre_calendar_exception`**, returning the
`kind` and the `note` together in one query. Readiness needs the note to name a
closure; the resolver uses only the kind. One function, one round trip, still
`collection_center` answering for its own table.

**`operational_readiness` no longer imports `CalendarEntry` at all.** That
import's absence is the architectural claim, and there is a test asserting it.

## 3. Architectural decision

**The defect this fixes is not cosmetic.** Readiness was correct about a centre
and blind to the organization: a dairy could declare a public holiday, the
delivery scheduler would suppress the round — and every centre would still
report itself **READY**. Two subsystems, two answers, one question.

The API contract is preserved exactly:

| Situation | Before | After |
|---|---|---|
| Nothing declared | blocking, passed, "no calendar exception today" | unchanged |
| Centre `closure`/`holiday` | blocking, failed, names kind and note | unchanged |
| Centre `special` | warning, failed, "special day today: …" | unchanged |
| **Organization holiday, no centre entry** | **passed — the defect** | blocking, failed, "organization calendar: not a working day" |

`special` is worth being explicit about. The resolver says a `special` day is
**worked**, so it is not a closure — and readiness still reports it as a
**warning**, exactly as before. The resolver decides *whether the day is
worked*; readiness adds *that it is not an ordinary one*. Those are different
statements and neither is a duplicate of the other.

No country appears anywhere in the change. The zone comes from the
organization the country registry configured at onboarding, and the same code
runs for every tenant.

## 4. Defects found

**One, and it is the milestone's subject**: an organization-level holiday did
not reach readiness. Proven by a test that asserts the ordinary day passes
first, then declares the holiday and watches the same centre become
`NOT_READY`.

No other independent working-day decision remains in production code.

## 5. Known limitations

* **Readiness evaluates "today" only.** It answers about the current business
  date, as it always has; there is no "will this centre be ready on Thursday".
* **The `special` warning is centre-only.** An organization-level `working:
  true` exception resolves to worked and produces no warning, because
  `organization_calendar_day` has no note-bearing equivalent of "unusual".
* **One extra query when a centre is shut.** The centre's entry is fetched to
  name the reason. On the common path — nothing declared — it is one lookup
  the resolver has already cached.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-023: readiness resolves through `WorkingDayResolver`; the last second reader of the working-day rule removed, with a source-level guard against its return. No schema change. |
