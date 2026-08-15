---
id: DEMO-020-FINAL
title: DEMO-020 — Global Business Calendar & Financial Period Foundation
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-019-FINAL, DEMO-018-FINAL, DEMO-017-FINAL, DEMO-014-FINAL, DEMO-013-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-020 — Global Business Calendar & Financial Period Foundation

An architecture milestone, and the survey it began with is most of the story:
**the business-date abstraction the work order asked for already existed and
was already authoritative.** DEMO-013 decided that the organization's timezone
governs its business date; DEMO-014 built the hierarchy above it; DEMO-019 made
the rule hold inside SQL. There was nothing to design.

What there was, was **four places still answering the question their own way**
— and, more seriously, **three PostgreSQL proofs that had never run.**

---

## 1. What already existed

| Capability | Where | Since |
|---|---|---|
| Business date from the organization's zone | `core/business_time.business_today` | DEMO-013 |
| Instant → business date | `business_date_of` | DEMO-013 |
| Local day → UTC window | `day_bounds`, `range_bounds` | DEMO-013 |
| Timezone hierarchy: organization → centre → user | `core/timezones.py` | DEMO-014 |
| The same rule inside SQL | `local_date_sql` | DEMO-019 |
| Scheduler running on each tenant's own clock | `delivery/scheduler.py` | DEMO-017 |
| Per-centre closures | `center_calendar_entry` | DEMO-005 |

The objective's chain — organization → country → currency → timezone →
optional centre timezone → user display preference → business date — was
already built, and `core/timezones.py` already states the rule that matters:
`business_timezone()` never consults a user, `display_timezone()` is the only
function that does, and nothing computing a date boundary may call it.

**So no second abstraction was created.** Everything below extends what was
there.

## 2. What DEMO-020 added

**Two facts the existing functions cannot derive**, because they are decisions
somebody makes rather than arithmetic:

* **`organization_calendar_day`** — a dated exception to the ordinary working
  week, with an explicit `working` flag. Organization-wide, above the existing
  per-centre closures.
* **`financial_period`** — a stretch of business dates with a status, and a
  guard that refuses writes into a closed one.

**One authoritative month and year mechanism.** `month_bounds` lost a
`timezone_name` parameter it never read; `previous_month_bounds` and
`business_year` were added; `billing/month_end.previous_month` collapsed from
hand-rolled arithmetic to one delegation.

## 3. The four places still answering their own way

**1. Document numbers used UTC's year.** `period_for()` defaulted to
`utcnow().date().year`, and all seven document series — invoices, payments,
receipts, settlements, customer codes — took it. A receipt handed over at 03:30
on 1 January in Bengaluru was stamped with the year that ended ninety minutes
earlier, on a sequential financial document several target jurisdictions
require to be exactly that. Kenya and Qatar were wrong for the same three
hours. Nothing failed, because the counter is per `(tenant, type, period)` and
simply kept counting in the old year.

**2. The reporting projection bucketed by UTC's day.** `ReportingProjection`
took `.date()` off the event instant — DEMO-019's trend-chart defect, in the
read model. It filed an Indian dairy's 05:00 collection under yesterday. No
production query reads those tables yet, which is the worst kind of wrong: it
would have been discovered by whoever first trusted it.

**3. `month_bounds` had an inert parameter.** It accepted a timezone and never
used it, so `month_bounds(utcnow().date(), tz)` read like a conversion,
converted nothing, and returned UTC's month under a local-looking name. For an
Indian dairy in the first 5½ hours of the 1st, that is the whole of the wrong
month's billing.

**4. `local_date_sql`'s docstring described the wrong expression** — the first
draft the DEMO-019 PostgreSQL test rejected. The reasoning survived the fix and
the summary above it did not.

## 4. The more serious find: proofs that never ran

`infra/ci/postgres-proof.sh` names its PostgreSQL-only suites in an explicit
list, above a comment saying to add new modules there. **Two were missing:**

* `test_business_date_sql_postgres.py` (DEMO-019) — the suite that caught a
  genuinely wrong SQL expression the entire rest of the suite passed over;
* `test_scheduler_concurrency_postgres.py` (DEMO-018) — the four-worker race.

Both had run once, by hand, and never in the pipeline. The script's own skip
assertion cannot catch this: **a file that is never named is never collected,
so it is never skipped either — it is simply absent, and the proof passes
without it.**

`test_no_postgres_only_suite_is_left_out_of_the_proof` now compares the list
against the files on disk. It found the second omission the moment it was
written.

**And adding them exposed why they had passed.** Both were run as `postgres`,
a superuser — and superusers ignore row-level security entirely, FORCE
included. Under the proof's unprivileged role they failed immediately:

* the DEMO-019 suite created a probe table and had no `CREATE` on `public`. It
  now binds a literal instead — the expression under test takes a timestamptz
  *expression*, not a stored column, so the same SQL is exercised with no
  schema rights at all;
* the DEMO-018 suite's tenant bindings were **no-ops**. `bind_tenant` and
  `bind_platform_context` return early unless `settings.database_url` says
  PostgreSQL, and conftest pins that to SQLite for the whole test process.
  `test_rls_postgres.py` has an autouse fixture for exactly this reason
  (VER-001); the newer suites never copied it. **A suite that appears to prove
  tenant isolation while every binding in it is inert is the defect this
  repository was built to distrust.**

Both now carry the fixture, and both run under the unprivileged role.

## 5. What did NOT change

**No historical financial record was touched.** The migration is purely
additive: two new tables, no column added to and no row modified in any
existing one.

**No existing behaviour changed.** `is_working_day` treats an absent row as a
working day — exactly the platform's behaviour before the table existed — and
the period guard permits any date not covered by a *closed* period. With both
tables empty, every guard passes. The capability begins to refuse only once
somebody deliberately declares a holiday or closes a month.

**The scheduler was not touched.** It already resolves each tenant's local date
and hour from that tenant's zone (`business_date_and_hour`). The work order
asked that it keep doing so; it does.

**Mobile was not touched.** `_deviceDate()` is documented as a last-resort
fallback and the round asks the platform by omitting the dates — mobile already
never decides the business date from device time. One diagnostic screen (the
pricing playground) defaults its date field from the device clock; it is an
editable input on a developer tool, and changing it was out of scope.

**The projection's meaning changed, so its version was bumped** to 2 rather
than rewriting rows underneath a reader. The platform now reports it as
outdated until an operator rebuilds — the honest handling.

## 6. What the deployment itself found

**The version bump failed the deployment gate, and that was correct.**

`verify-deployment.sh` treats a projection registry warning as a failed
deployment. Bumping the projection to version 2 marks the built data outdated
— deliberately — so the first deploy failed on `projections: warning`, rolled
back, and the rollback then failed its own schema check because the schema had
already moved forward while the code went back.

The platform kept serving throughout (the API stayed healthy, the mixed state
was an additive schema under older code, which is exactly the case an
expand-only migration is designed to survive). But it is worth being precise
about what happened: **a milestone that deliberately marks a read model stale
cannot deploy without performing the rebuild the staleness demands.** The
resolution was to deploy with `--no-rollback`, run the rebuild — 8,146 events
scanned, 534 applied, 59 stale rows removed, completing at version 2 — and then
re-run the gate, which passed on its own terms.

Nothing was forced and no check was weakened. The gate asked for an operator
action and got it.

A second, smaller observation: immediately after a rebuild the `consumers`
probe reports a transient warning, because the rebuild moves the cursor and the
sampled snapshot catches it mid-flight. It clears on the next sample.

## 6. Known limitations

* **Organization holidays do not affect delivery generation or readiness.**
  The work order says not to change existing delivery behaviour unless a
  business rule requires it. The calendar is readable and enforced nowhere yet;
  wiring it into the scheduler is a behaviour change and belongs to whoever
  asks for it.
* **The period guard is available and not yet called by billing or
  settlement.** `assert_open()` exists, is tested, and refuses — but no
  existing write path calls it, because doing so would change behaviour for
  organizations that have declared periods without being asked. The
  foundation is what this milestone was scoped to.
* **Centre-level and organization-level calendars are separate tables.** They
  answer to different owners and are read by different rules; merging them
  would have made one module query another's rows. There is no resolution
  order between them yet.
* **No weekly non-working pattern.** `delivery_plan.weekdays` already carries
  one, per customer, and a second coarser pattern would give two answers to
  one question.
* **The rollback pin now points at the same release.** DEMO-020 was deployed
  twice with the same tag (once with `--no-rollback` to perform the rebuild,
  once cleanly), so `deploy.sh --rollback` would be a no-op. The genuine
  previous release, `main-93affa5`, is still on disk and can be deployed by
  tag — but because the schema moved, a true rollback also needs
  `alembic downgrade -1`. The migration is expand-only, so the older code runs
  correctly against the newer schema; only the verifier's schema-equality
  check objects.
* **`period_for` is still year-based.** A market needing a fiscal year that
  does not start in January changes that one function, as its original comment
  anticipated.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-020: the business calendar made a platform capability — organization working days and financial periods with a guard that refuses; four modules brought onto the one authoritative business-date rule; and three PostgreSQL proofs that had never run in the pipeline found, fixed and wired in. |
