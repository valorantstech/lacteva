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

## 5. Verification

**Tests:** 1,566 backend passing, 0 failures (95 skipped — the PostgreSQL-only
suites, which then ran for real). 252 portal, 125 mobile, lint/format/tsc/build
and docs/xref green. **No migration** — the change is code only, and the
migration count is unchanged at 42.

16 new tests. The load-bearing one is a parametrized property asserting that
**readiness and the resolver return the same decision across all seven
combinations the model can express**, asked through two different doors — the
HTTP endpoint and the resolver directly — so it fails if either side is changed
alone. Both guarantees were mutation-checked: making readiness ignore the
resolver fails seven tests, and restoring the direct `CalendarEntry` import
fails the source guard.

**PostgreSQL proof PASSED** — 95 PostgreSQL-only tests, **0 skipped**, 65 tables
RLS-enabled and forced, migrations from empty, source and restored identical.

**Production, `main-9c110b7`, deployed first attempt** with verification and
smoke test passing. Schema unchanged at `b8d3e1470f92` — nothing to migrate.
All nine health checks healthy; 65/65 tables forced.

**Read-only production verification, exactly as the work order required — no
holiday and no financial record was manufactured.** For every centre of every
tenant, the resolver's answer and the readiness engine's calendar verdict were
compared directly:

| Tenant | Zone | Business date | Centres agreeing |
|---|---|---|---|
| Lacteva Demo Cooperative | Africa/Nairobi | 2026-08-15 | 2 / 2, both READY |
| Lacteva India Demo | Asia/Kolkata | 2026-08-15 | 2 / 2, both READY |
| Lacteva Isolation Demo | Africa/Nairobi | 2026-08-15 | 1 / 1 |
| Phoenix Demo Dairy | Asia/Kolkata | 2026-08-15 | 1 / 1 |

**Financial reconciliation: every count identical** before and after
(collections 534, deliveries 1255, invoices 31, customer payments/receipts
24/24, settlements 84, supplier payments/receipts 42/36); receivables unchanged
at **211,961.00 KES** and **152,972.00 INR**.

**Browser:** the Kiambu Highlands Centre page renders Readiness as **ready**
with `center calendar` passing, alongside the operating hours and activity
figures — the contract an operator sees is visibly unchanged.

**Rollback:** previous release `main-d03a658` is on disk and pinned. The schema
did not move, so `deploy.sh --rollback` is sufficient with no downgrade.

**AWS: nothing created, nothing modified, no recurring cost change.** One
security-group SSH rule was rotated to the current workstation address, the
stale `/32` revoked — same posture, one workstation, not a widening.

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
