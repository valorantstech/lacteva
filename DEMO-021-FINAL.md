---
id: DEMO-021-FINAL
title: DEMO-021 — Organization Calendar Resolution & Financial Period Operations
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-020-FINAL, DEMO-019-FINAL, DEMO-014-FINAL, DEMO-013-FINAL, CON-0001]
baseline: ARCH-BASELINE-V1
---

# DEMO-021 — Organization Calendar Resolution & Financial Period Operations

DEMO-020 built a calendar and a financial period, and connected them to
nothing. It said so at the time, in three known limitations. This milestone is
those three limitations, closed — and **no schema change was needed to close
them**, which is the clearest evidence the previous milestone's shape was
right.

---

## 1. What already existed

Everything about *what day it is*, and it was already authoritative:

| Capability | Where | Since |
|---|---|---|
| Business date from the organization's zone | `business_today`, `business_date_of` | DEMO-013 |
| Local day → UTC window | `day_bounds`, `range_bounds` | DEMO-013 |
| Timezone hierarchy: organization → centre → user (display only) | `core/timezones.py` | DEMO-014 |
| The same bucketing inside SQL | `local_date_sql` | DEMO-019 |
| Month, previous month, business year | `month_bounds`, `previous_month_bounds`, `business_year` | DEMO-020 |
| `organization_calendar_day`, `financial_period`, and a guard | `modules/business_calendar` | DEMO-020 |
| Per-centre closures | `center_calendar_entry` | DEMO-005 |

The survey found the reporting audit already complete: no `date.today()`, no
`utcnow().date()`, and no naive UTC month remained anywhere in the source. The
scheduler already resolved each tenant's local date and hour from that tenant's
own zone.

**What was missing was operational, not architectural.** The guard was called
by nothing but its own API, and the two calendars had no resolution between
them.

## 2. What DEMO-021 changed

**Resolution is now deterministic, and structurally cannot consult a person.**
`resolve_working_day(organization=…, centre=…)` is a pure function over values:
the centre's opinion wins where it has one, otherwise the organization's,
otherwise the day is a working day. `None` means "no opinion" and is
deliberately distinct from `False`.

Because it is a function over values, neither module queries the other's
tables — the API layer asks `collection_center` for the centre's `kind`, asks
`business_calendar` for the organization's flag, and hands both in.
`GET /v1/organization/calendar?center_id=…` is the composed endpoint.

`centre_exception_is_working(kind)` writes down the mapping the readiness
engine has used since DEMO-005: `holiday` and `closure` stop work, `special`
does not.

**A user's display timezone cannot reach a business date, and that is now
asserted at the seam** rather than assumed: `business_timezone` does not accept
a user timezone — passing one is a `TypeError`, not a wrong answer — while
`display_timezone` accepts and honours it.

**The closed-period guard now protects the paths that commit money:**

| Path | The date it is guarded by |
|---|---|
| Generate an invoice | the period it bills |
| Issue an invoice | the period it bills |
| Cancel an invoice | the period it bills |
| Record a customer payment | the day the money arrived |
| Finalize a settlement | the period it settles |
| Create a supplier payment | the day the dairy decided to pay |

Each of those dates is the one the record *belongs* to, not today's. Guarding
an invoice by today would let somebody bill a closed August from an open
September.

**Deliberately not guarded:** event consumers, and the payment completion path.
A consumer that raised would dead-letter a fact that has already happened, and
refusing at `complete` would strand money mid-flight. Closing a period stops
people making new decisions; it must not stop the platform finishing ones
already made.

**The portal makes it usable**: calendar exceptions are listed, a period can be
declared for the previous month, and open periods can be closed and closed ones
reopened.

**Documentation**: `CON-0001 Business Calendar` states the whole model in one
page, and the glossary gains *Business Date* and *Financial Period* pointing at
it.

## 3. Defects discovered

**One, in my own DEMO-020 code: the refusal was implemented twice.**
`BusinessCalendarService.assert_open` and the module-level `assert_period_open`
each built the same `ConflictError` from the same guard. Two copies of "what a
closed period does" is the kind of duplicate that drifts silently — a caller
using the stale copy would simply stop refusing. The module function now
delegates to the method, and there is one implementation.

**It was found by a mutation check that first gave a false negative**, which is
worth recording. Disabling the guard left every test passing — because the
mutation had hit the *first* of the two identical lines, the method, while the
financial paths called the *second*, the function. The duplication and the
misleading result had the same root cause. With one implementation, disabling
the guard fails four tests, which is the check the milestone actually needed.

No defect was found in the existing business-date machinery. The reporting
audit, the scheduler and the month/year boundaries were already correct, and
this milestone's tests confirm rather than repair them.

## 4. What did NOT change

**No schema change.** `alembic --autogenerate` produces an empty diff. The
migration steps in the work order's §13 reduce to verifying that, which was
done.

**No historical financial record was touched**, and no existing behaviour
changed for any organization that has not closed a period: the guard is
permissive by construction, and there are none closed in production.

**The scheduler was not touched.** A declared holiday does not stop a delivery
round. The work order asked that scheduler behaviour not change merely because
a holiday table exists, and it has not — a dairy's actual schedule lives in
`delivery_plan.weekdays`, per customer. This is recorded as a limitation rather
than left implicit.

**Mobile was not touched.** It obtains business dates from the platform by
omitting them from report calls; its `_deviceDate()` is a documented
last-resort fallback. Nothing in DEMO-021 changes what it consumes.

## 5. Known limitations

* **Holidays are advisory.** They are recorded, resolved and reported, and
  enforced nowhere. Making a holiday suppress generation is a behaviour change
  that belongs to whoever asks for it, with its own tests and rollout.
* **Centre resolution is available on one endpoint.** `GET
  /v1/organization/calendar?center_id=…` composes it; no other caller passes a
  centre yet, and the readiness engine still reads its own centre calendar
  directly rather than through `resolve_working_day`.
* **The guard is on write paths, not on amendments to already-closed
  documents.** Immutability is enforced separately and already: issued
  invoices, finalized settlements and completed payments cannot be edited at
  all, in any period.
* **No Qatar tenant exists in production**, deliberately. Qatar is verified in
  tests and against the registry; the work order forbade creating a fake tenant
  in production to prove it.
* **One lookup per guarded write.** An indexed single-row SELECT on
  `financial_period`, on write paths only — no read path pays for it.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-021: deterministic calendar resolution as a pure function, the closed-period guard wired into every path that commits money, the duplicate refusal collapsed, and the model written down as CON-0001. No schema change. |
