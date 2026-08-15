---
id: CON-0001
title: Business Calendar
type: con
status: Approved
version: "1.1"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-021-FINAL, DEMO-020-FINAL, DEMO-019-FINAL, DEMO-014-FINAL, DEMO-013-FINAL]
baseline: ARCH-BASELINE-V1
---

# The Business Calendar

The one place that answers: **which day is it for this dairy, does it work that
day, and may that day still be written to?**

Everything here is already implemented. This document exists because the rules
are spread across four modules by design, and a reader needs one page that says
how they fit — not because the code needs an explanation to be correct.

---

## 1. Storage is UTC. Interpretation is the organization's.

Every timestamp column is `DateTime(timezone=True)` and every row is stamped
with `utcnow()`. That does not change and must not: a canonical instant is the
only thing that survives a server move, a restore into another region, or two
tenants in different zones sharing a database.

What is *interpreted* is which local calendar day an instant belongs to, and
that is a business fact rather than a storage one.

| Question | Function | Module |
|---|---|---|
| What day is it for this organization, now? | `business_today(tz)` | `core/business_time.py` |
| Which day does this stored instant belong to? | `business_date_of(instant, tz)` | `core/business_time.py` |
| Which UTC window covers that local day? | `day_bounds`, `range_bounds` | `core/business_time.py` |
| The same bucketing, inside SQL | `local_date_sql(col, tz, dialect)` | `core/business_time.py` |
| Which month / year is that date in? | `month_bounds`, `previous_month_bounds`, `business_year` | `core/business_time.py` |

**A business date is never derived by truncating a UTC timestamp.** DEMO-019
found that defect in the procurement reports — for a Nairobi cooperative after
local midnight the window began three hours in the future, and the daily
collection report read zero for a day milk had been collected.

## 2. The timezone hierarchy

    organization   →  the business clock. Always set (resolved from the
                      country at onboarding) and always the answer unless
                      something more specific applies.

    collection centre → an OPTIONAL override, for a cooperative that spans a
                      border. Null means "my organization's".

    user           →  DISPLAY ONLY.

`core/timezones.business_timezone(org, centre)` resolves the first two.
`display_timezone(org, user, centre)` is **the only function on the platform
that consults a person**, and nothing that computes a date boundary may call
it.

That separation is structural, not a convention: `business_timezone` does not
take a user timezone parameter, so "a manager flew to London and the dairy's
accounting day moved" is not a defect this design can have.

## 3. Working days

Two tables, two scopes, one resolution:

| Scope | Table | Owner | Since |
|---|---|---|---|
| Organization-wide | `organization_calendar_day` | `business_calendar` | DEMO-020 |
| One centre | `center_calendar_entry` | `collection_center` | DEMO-005 |

`resolve_working_day(organization=…, centre=…)` decides between them, and it is
a **pure function over values**:

* the centre's opinion wins where it has one;
* otherwise the organization's;
* otherwise the day is a **working day**.

`None` at a level means "no opinion", which is deliberately different from
`False`. The default is `True` because that is what the platform did before any
calendar existed — an absent row must never turn a working day into a holiday.

Because resolution is a pure function, neither module queries the other's
tables. The caller that has a centre in scope asks `collection_center` for the
centre's `kind`, asks `business_calendar` for the organization's flag, and
hands both in. The composition happens in the API layer, which is the
composition root.

`centre_exception_is_working(kind)` maps the older `kind` vocabulary onto the
flag: `holiday` and `closure` stop work, `special` does not — the same reading
the readiness engine has used since DEMO-005.

**Working days suppress automatic delivery generation** (DEMO-022). The
scheduler resolves each due plan against its own centre's calendar through
`WorkingDayResolver` — the one path — and a non-working answer skips the plan.
See §6.

`WorkingDayResolver` is the only thing that should ever perform this
resolution. It caches per centre for the life of one day's run, so a round of
three hundred plans across five centres costs six lookups, and it reads the
centre's opinion through `collection_center`'s own service function rather
than its table.

## 4. Financial periods

A period is a range of **business dates** with a status:

    OPEN  ⇄  CLOSED

Two states and no more. "Locked", "provisional" and "under review" are the
states that turn a boundary into a workflow engine.

The dates stored are *local* business dates — August for an Indian dairy is
2026-08-01 to 2026-08-31, which begins at 18:30 UTC on 31 July and ends at
18:30 UTC on 31 August. Storing the local dates and converting at the edges is
what keeps that true; storing a UTC instant pair would bake in the conversion
and lose five and a half hours at both ends.

Reopening is deliberately possible and separately permissioned. A month closed
by mistake would otherwise be unbillable forever, which is a worse failure than
the one closing prevents.

## 5. Closed-period protection

`assert_period_open(session, tenant, day, operation=…)` is the single call
other modules make. It refuses when `day` falls inside a **closed** period.

**Which date to hand it is the caller's judgement**, because only the caller
knows which date the record belongs to:

| Operation | The date it belongs to |
|---|---|
| Generate / issue / cancel an invoice | the period it bills (`period_to`) |
| Record a customer payment | the day the money arrived |
| Finalize a settlement | the period it settles (`period_to`) |
| Create a supplier payment | the day the dairy decided to pay |

Guarding an invoice by *today's* date would let somebody bill a closed August
from an open September. That is the subtle failure this table exists to
prevent.

**The guard is not called from event consumers**, and that is a decision. A
consumer that raised here would dead-letter a business fact that has already
happened — the payment was taken; the receipt is merely its consequence.
Closing a period must stop people making new decisions, not stop the platform
finishing ones already made. It is therefore on operator-initiated application
service calls only.

**It is permissive by construction.** A tenant with no periods has none
closed, so every date passes. That is what made it safe to introduce into a
running platform, and it is asserted in the tests rather than assumed.

Completion paths — `payment.complete`, `payment.execute` — are deliberately
*not* guarded, for the same reason as consumers: refusing there would strand
money mid-flight.

## 6. Holidays and the scheduler

A non-working business date suppresses **automatic** delivery generation for
the plans it covers. Three rules make that safe:

1. **Automatic only.** The manual generation endpoint is unchanged and is not
   calendar-suppressed. An operator asking for a round on a declared holiday
   knows something the calendar does not; the scheduler is nobody.
2. **Nothing already made is touched.** The calendar governs generation that
   has not happened yet. Declaring a holiday after a round has gone out
   deletes no delivery, reverses no invoice and rewrites no history.
3. **No backfill, ever.** A suppressed day is recorded as `holiday`, which is
   a *finished* status alongside `success` — so the loop does not re-ask, and
   the next day generates only itself. Monday shut means Monday is empty and
   Tuesday is Tuesday.

The run row carries `skipped_holiday`, separate from `not_due`, because "the
dairy was shut" and "these households do not take milk today" are different
answers to an operator asking why a round is short.

## 7. What this is not

* **Not a scheduling engine.** Suppression is a filter over plans the existing
  generator already produces. A dairy's actual schedule still lives in
  `delivery_plan.weekdays`, per customer.
* **Not an accounting system.** Closing a period posts no journal, rolls no
  balance and computes no trial balance. It refuses writes and nothing else.
* **Not a weekly pattern.** There is no organization-wide "closed on Sundays";
  `delivery_plan.weekdays` already carries one per customer, and a second,
  coarser pattern would give two answers to one question.
* **Not user-configurable resolution.** The hierarchy is fixed. A tenant
  cannot elect to have user timezones drive its accounting dates.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-15 | Platform Engineering | DEMO-022: holidays now suppress automatic delivery generation; `WorkingDayResolver` named as the one resolution path. |
| 1.0 | 2026-08-15 | Platform Engineering | Written in DEMO-021, describing the calendar as it stands after DEMO-013, DEMO-014, DEMO-019, DEMO-020 and DEMO-021's resolution and guard work. |
