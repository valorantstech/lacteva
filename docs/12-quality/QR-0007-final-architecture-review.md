---
id: QR-0007
title: Final Enterprise Architecture Review & v1.0 Freeze (ARCH-FINAL-001)
type: qr
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-08
last-updated: 2026-08-08
related: [STD-0007, QR-0006, DBD-0001, API-0001, CAP-0001]
baseline: ARCH-BASELINE-V1
---

# QR-0007 — Final Enterprise Architecture Review & v1.0 Freeze

Independent technical sign-off before pilot deployment. Every subsystem was
reviewed as a Principal Architect would review a platform they will be paged
for: business rules, security, platform, database, infrastructure, API and
codebase. Coding style is out of scope and was ignored.

The review followed this repository's own doctrine — **execute, do not read**
— so the findings below distinguish what was *proven by running it* from what
remains asserted.

---

## 1. Executive Summary

Lacteva's backend is a genuinely well-built platform. The architecture is
coherent, the boundaries are real, and — unusually — the documentation is
honest about what it has not done. The divergence register in
[CLAUDE_CONTEXT](../ai/CLAUDE_CONTEXT.md) is the single most valuable
engineering artifact in the repository: forty-five recorded weaknesses, most
of them found by the team itself, none of them hidden. Very few platforms at
this stage can be reviewed this quickly, and the reason is that the previous
work orders did the hard part already.

The core money path is correct. I re-executed the guarantee that matters most
— that two concurrent payments cannot each claim the same settlement's full
balance — against a real PostgreSQL engine, and it holds.

**But its proof did not.** The two tests pinning that CRITICAL fix were
`inspect.getsource()` string matches asserting the characters
`with_for_update=True` appear in the method. A source grep cannot distinguish
a working lock from a lock that is silently a no-op, and `FOR UPDATE` **is**
a no-op on SQLite, so nothing in the 1,014-test suite could have caught its
removal. That is precisely the failure STD-0007 §6 exists to forbid, sitting
on top of the platform's most valuable invariant.

Executing it properly then found a **new defect the lock itself introduced**:
`create()` acquired settlement locks in client-supplied order, so two payments
allocating the same two settlements in opposite order deadlocked. Reproduced
against real PostgreSQL (SQLSTATE 40P01), fixed by deterministic lock
ordering, and the fix verified by reverting it and watching the new test fail.

A second class of finding is more worrying than any individual bug: **three of
the platform's production defaults are configured to look healthy while doing
nothing.** Both notification channels default to providers that mark every
message delivered and send nothing, and `LACTEVA_RLS_ENABLED=false` removes
the tenant boundary *and* silences the startup check that would report its
absence. All three are now refused at startup in `prod`.

What I cannot sign off is the **operational** half. The production stack has
never been executed — no Docker, no host, no Terraform apply, no staging
environment. The deployment automation, the nginx configuration, the systemd
units and the infrastructure code have been validated by parsing and by tests
that read their contents. On a platform whose own history contains four
separate cases of "written, reviewed, CI-wired, and completely broken on first
execution", that is not a small residual risk. It is the same risk, one layer
down, and it has not yet been retired.

**Verdict:** the backend is architecturally ready and functionally sound.
Deployment is unrehearsed and backups are not independently durable. Both are
fixable in days, and neither requires a code change.

---

## 2. Architecture Score

**8.5 / 10**

| Dimension | Score | Note |
| --- | --- | --- |
| Module boundaries & dependency direction | 9.5 | Bounded contexts are real; cross-module access is by id and events only. No circular imports. Genuinely extractable services. |
| Event architecture (outbox, consumers, projections) | 9.5 | Transactional outbox, cursor-over-log consumers, idempotency ledger, rebuildable projections with drift detection. Best-in-class for this size. |
| Security architecture | 9.0 | RS256 with a key registry, RLS with a closed table taxonomy, audited bypass with a dedicated factory. Deep and well-reasoned. |
| Domain modelling | 8.5 | Immutability as a first-class state, CAS transitions, registry-defined business rules cited by enforcing code. |
| API design | 8.5 | 177 operations, RFC-9457 throughout, declared bounds, platform-wide idempotency. Missing `ETag`. |
| Data architecture | 6.0 | **The weak point.** Four foreign keys and a handful of check constraints in a 56-table schema; float columns still under the pricing bands; no partitioning. |
| Decision record | 4.0 | **Zero ADRs.** The stack was dictated, not decided-by-record. For a v1.0 freeze this is a real gap. |

The deduction is concentrated, not diffuse. Everything about *behaviour* is
strong; what is weak is everything about *durable structure* — referential
integrity, storage types, and the written record of why the architecture is
what it is.

---

## 3. Production Readiness Score

**6.5 / 10** — ready for a controlled pilot once §9 is complete; not yet ready
for an unattended production service.

| Dimension | Score | Basis |
| --- | --- | --- |
| Correctness under concurrency | 9.0 | Executed this review against real PostgreSQL, including a control proving the test can fail. |
| Backup / restore / PITR | 8.5 | All three executed against real clusters. Undermined by backups sharing the database volume. |
| Data isolation (RLS) | 9.0 | Executed; policies forced; superuser refused at startup; every table classified. |
| Observability | 8.0 | 50 metrics, four-level health, 12 actionable alerts, correlation ids across process boundaries. |
| Deployment | 3.0 | **Never executed.** No Docker or host in any environment that has touched this repository. |
| Infrastructure as code | 3.0 | **Never applied.** First `terraform plan` is a review step, not a formality. |
| Scale headroom | 5.0 | No load testing at all. Consumer scan and unbounded log growth are structural ceilings. |
| Data lifecycle | 2.0 | No retention, no archival, no tenant deletion, no right-to-erasure path. |

---

## 4. Critical Issues

Two. Neither is a code defect; both block an *unattended* pilot.

### C-1 — The production stack has never been executed

`docker-compose.production.yml`, the nginx configuration, the systemd units,
`deploy.sh`, `verify-deployment.sh` and `smoke-test.py` have been validated by
parsing them and by tests that assert their contents. No environment that has
ever touched this repository had Docker, a host, or a cloud account. Terraform
has never been applied.

**Why this is Critical rather than Medium.** This platform's own history is the
argument. VER-001, DR-001, PITR-001 and CI-001 did nothing but *execute*
guarantees that were already written, reviewed and CI-wired, and found fourteen
defects — including one that made the platform unable to serve a single request
on PostgreSQL. The deployment layer is at exactly the maturity the database
layer was at before VER-001: carefully written, plausibly correct, unexecuted.

**Recommendation.** Stand up one throwaway host and run the full sequence —
`terraform plan`/`apply`, cloud-init, `deploy.sh`, `verify-deployment.sh`,
`smoke-test.py`, then a deliberate rollback. Expect defects; that is the point.
Do not let the pilot dairy be the first execution.

### C-2 — Backups live on the same volume as the database

Recorded as divergence #40. The logical backups, the physical base backups and
the WAL archive all sit on the volume that holds the cluster. A volume loss —
the most common single failure for a single-host deployment — destroys the
data and every means of recovering it simultaneously. Provider snapshots are
the only independent copy, and nothing in the platform verifies they exist.

The DR and PITR proofs are excellent and genuinely executed. They restore
*from a backup that may not survive the incident that requires it*.

**Recommendation.** Ship logical backups off-host before the pilot (object
storage with versioning and a lifecycle policy is sufficient), and extend the
weekly restore verification to pull from the off-host copy rather than the
local one. This is the highest-value infrastructure work remaining and it is
roughly a day.

---

## 5. High Priority Issues

### H-1 — Deadlock on multi-settlement payments *(found and fixed in this review)*

`PaymentService.create` locked each allocated settlement `FOR UPDATE` in the
order the **client** supplied. Two payments allocating the same two settlements
in opposite order took the same two row locks in opposite order — a textbook
deadlock cycle. A supplier with two unpaid settlements and two operators is all
it takes; no unusual usage is required.

Reproduced against real PostgreSQL: one transaction aborts with
`DeadlockDetectedError` (SQLSTATE 40P01), surfacing to the operator as a 500
while trying to pay a farmer. No data corruption — PostgreSQL aborts cleanly —
but an unhandled failure on the money path.

**Fixed.** `create()` now sorts allocations by settlement id, so every
transaction in the platform acquires these locks in the same sequence and no
cycle can form. Covered by `test_opposite_order_allocations_do_not_deadlock`,
which was verified to fail (with the deadlock) when the ordering is removed.

### H-2 — The platform's most critical guarantee had no executable proof *(fixed)*

The two tests pinning ARCH-001's double-payment fix were `inspect.getsource()`
string matches. `FOR UPDATE` is a no-op on SQLite, so the main suite could not
have proven the guarantee even if it had tried to execute it.

**Fixed.** `tests/test_payment_concurrency_postgres.py` runs the actual race on
a real engine, in separate sessions and separate transactions, and includes a
**control** that removes the lock and asserts the double payment *does* occur
(2000.00 allocated against a 1000.00 payable). Without the control the passing
test would prove nothing. Wired into `infra/ci/postgres-proof.sh`, where a skip
is a hard failure.

The structural canaries in `test_production_readiness.py` were kept — they are
fast and catch an accidental deletion on every push — but are now documented as
canaries rather than proofs.

### H-3 — Both notification channels default to reporting success and sending nothing *(fixed)*

`notification_sms_provider` and `notification_email_provider` both default to
`logging`, whose `send()` returns `ACCEPTED`. In production that means: the
message renders, the delivery row records acceptance, retry logic never fires,
every dashboard is green, and the supplier is told nothing. `placeholder`
behaves identically.

A production deployment that changes nothing gets a messaging platform that
silently discards every message. This is the "looks healthy while doing
nothing" failure shape the platform's own observability doctrine names as its
most dangerous — reachable by doing nothing at all.

**Fixed.** `prod` now refuses `logging` and `placeholder` on either channel.
`dry_run` (a real message against real configuration, deliberately not sent)
and `disabled` (raises, so the delivery visibly fails and dead-letters) remain
available. Email has no transport at all, so a production deployment must now
declare that explicitly rather than pretend.

### H-4 — Every consumer scans the entire event log, one transaction per skipped event

`ConsumerRunner._next_events` reads the outbox by keyset pagination with no
filter on `event_name`. Events the consumer does not handle are skipped in
Python — and each skip calls `_advance`, which opens **its own session and
commits**. With *N* registered consumers and *M* events, the platform performs
O(N × M) cursor-update transactions, almost all of them pure overhead.

At a modest dairy — 20,000 collections/day, ~60,000 events/day, four
consumers — that is roughly 240,000 single-row commit-per-event transactions
per day of waste, each with its own fsync. It is not a pilot blocker at one
dairy, but it is a hard throughput ceiling and the first thing that will bite
at scale.

**Not implemented.** The fix (filter by `event_name` in SQL; advance the cursor
once per batch) touches the ordering guarantees of BR-0013/BR-0014, which are
delicate and deserve their own work order with its own tests. Recommended for
the first post-freeze increment.

### H-5 — No data lifecycle: nothing is ever deleted

Recorded as divergence #34, and confirmed: there is no retention, archival,
partitioning or tenant-deletion path anywhere. `event_outbox`,
`event_delivery` and `consumer_execution` in particular grow without bound —
`consumer_execution` holds one row per consumer per event, forever.

Two consequences, and the second is the serious one:

1. Storage grows monotonically (~12 TB/year at the modelled scale, per
   DBR-001 F-3). Not a pilot problem.
2. **A tenant's data cannot be deleted.** A pilot customer who withdraws, or
   exercises a right to erasure, cannot be served — there is no code path, and
   the immutability rules that protect the audit trail actively work against
   one. This needs a decision (and probably a documented legal position)
   before a real customer's data enters the platform, not after.

### H-6 — Background workers are per-process, and the deploy has a gap

Divergences #37 and #42 combine badly. Workers are per-process loops, so two
API hosts run two relays and two consumer runners — safe by CAS and the
idempotency ledger, but never tested. Meanwhile Compose stops the old API
container before starting the new one, so every deploy has a 502 window.

The pilot's mitigation is "run workers on exactly one host", which is a
constraint no code enforces. Someone will eventually scale the API to two
replicas and silently double the polling.

**Recommendation.** Make it explicit: a `LACTEVA_WORKERS_ENABLED` flag,
defaulting on, so the second replica is deliberately started without them.

---

## 6. Medium Issues

### M-1 — Financial document numbers are random 24-bit hex

`Settlement`, `Payment` and `Receipt` numbers are generated as
`secrets.token_hex(3)` — 16.7 million values — inside a check-then-act loop
that retries five times against a `SELECT`.

Two problems. The smaller one is the race: two concurrent creations can
generate the same candidate, both see it free, and one fails on the unique
constraint with a 500. The larger one is regulatory: settlements, payments and
especially **receipts are financial documents**, and many of the fifty
jurisdictions this platform targets require gapless sequential numbering for
tax audit. A random hex string cannot satisfy that, and retrofitting sequence
semantics after a pilot's documents exist is considerably harder than deciding
it now.

### M-2 — Float columns remain under the pricing bands

Divergence #33. `pricing_matrix_row.unit_price`, `from_value` and `to_value`,
plus the three `milk_collection_transaction` weight columns, are still
`FLOAT`. DB-002 made every *aggregation* over them exact; storage was not
changed. Band boundaries are therefore still compared as floats, and BR-0005's
exact arithmetic starts from an inexact input. The next SQL expression written
over these columns reintroduces the problem silently.

### M-3 — Four foreign keys in a 56-table schema

Divergence #32. Cross-module absence is a defensible modular-monolith choice.
Intra-module absence is not, and `backup/integrity.py` compensating with orphan
detection *after the fact* is a workaround, not a design. Every denormalised
`tenant_id` added by SEC-002 is kept correct by service-layer discipline alone.

### M-4 — No optimistic concurrency on ordinary edits

Divergence #45. Lifecycle transitions are CAS-guarded, but concurrent edits to
free fields are last-writer-wins and neither client is told. Two operators
editing one supplier silently discard one set of changes. `ETag`/`If-Match` on
mutable resources is the conventional answer.

### M-5 — Rate limiting is fixed-window, fail-open, and per-process in memory

Divergence #21 plus the `memory` backend. Fail-open is a defensible choice for
milk collection. The combination with a per-process memory backend is not: two
replicas give an attacker twice the budget, and nothing warns.

### M-6 — Production does not refuse default database credentials

`database_url` defaults to `postgresql+asyncpg://lacteva:lacteva@localhost:5432/lacteva`.
The prod validator refuses a dev JWT secret, a dev MinIO secret, debug mode and
wildcard CORS — but not this. It is the same class of mistake and should join
the list.

### M-7 — Zero ADRs

Divergence #2. For a platform declaring a v1.0 architecture freeze, having no
architectural decision records at all is a structural gap. The freeze is the
moment to write them: they are cheapest now and most valuable in eighteen
months when someone asks why the outbox is not Kafka.

---

## 7. Low Priority Improvements

- **Tracing spans only at the HTTP and consumer seams** (#24). Outbox, payment
  and projection spans are one-liners against seams that already exist.
- **Health probes are uncached** (#25), so an aggressive poller creates load.
- **No PDF engine** (#16) and receipts carry no branding, localisation or QR
  verification (#17). A receipt that cannot be printed is a limited receipt.
- **Notification templates are code, not tenant data** (#11). A tenant cannot
  reword a message or add a locale without a deploy.
- **13 `JSON` columns should be `JSONB`** and append-heavy tables should use
  UUIDv7 rather than random v4 keys (#35) — the latter matters for index
  locality at volume.
- **Offline is single-writer** (#18) with no offline first-login or cached
  reference data (#19).
- **`_tenant_of` decodes the bearer token a second time** on every idempotent
  request. Correct and cheap, but it is a second trust decision in a second
  place; a note pointing at `deps.py` would help the next reader.

---

## 8. Technical Debt

Ranked by what it will cost to carry, not by size.

| # | Debt | Cost of carrying |
| --- | --- | --- |
| 1 | No data lifecycle (H-5) | Grows daily and blocks tenant offboarding. Cheapest to design before the first customer's data exists. |
| 2 | Consumer log scan (H-4) | Fixed ceiling on throughput; the fix gets harder as more consumers register. |
| 3 | Deployment never executed (C-1) | Retired by one afternoon on a throwaway host. Pure risk until then. |
| 4 | Float pricing columns (M-2) | One migration today; a data-correction exercise once real prices exist. |
| 5 | Missing referential integrity (M-3) | Every new module inherits the discipline requirement. |
| 6 | Random document numbers (M-1) | Nearly free now; a numbering migration across historical financial documents later. |
| 7 | Zero ADRs (M-7) | Compounds — the reasoning is in people's heads and this platform is explicitly built to outlive them. |
| 8 | Email has no transport (#12) | Bounded, but currently invisible; H-3's fix makes it visible. |

The team's own divergence register already tracks all of these except the ones
this review added. It should remain the single list.

---

## 9. Recommended v1.0 Freeze Checklist

Ordered. Items 1–4 are the gate; the rest are strongly recommended.

1. **Rehearse the deployment end to end on a throwaway host** (C-1) —
   `terraform apply`, cloud-init, `deploy.sh`, `verify-deployment.sh`,
   `smoke-test.py`, an upgrade, and a deliberate rollback. Record what breaks.
2. **Ship backups off-host** (C-2) and point the weekly restore verification at
   the off-host copy.
3. **Run `postgres-proof.sh` green**, including the new concurrency suite, on
   both PostgreSQL 16 and 17.
4. **Set every production configuration value explicitly** — the notification
   providers on both channels, `LACTEVA_RLS_ENABLED=true`, the database URL,
   CORS origins, JWT keys, MinIO credentials. The startup validator now refuses
   the dangerous defaults; confirm the deployment satisfies it rather than
   discovering it at boot.
5. **Confirm the application database role is `NOSUPERUSER NOBYPASSRLS`** on the
   real production cluster. This is the single check that decides whether RLS
   is enforcing anything at all.
6. **Decide the tenant-deletion position** (H-5) and write it down, even if the
   decision is "manual, documented, and out of scope for the pilot".
7. **Pin the workers-on-one-host constraint in configuration** (H-6).
8. **Write the founding ADRs** (M-7) — modular monolith, outbox over a broker,
   RLS for tenancy, SQLAlchemy models as entities, Decimal money policy. Five
   documents, and the freeze is the right moment.
9. **Agree the document-numbering policy** (M-1) before the pilot mints
   financial documents that would need renumbering.

---

## 10. Recommended Roadmap After Backend Freeze

**Phase 1 — Retire the operational unknowns (1–2 weeks).** Items 1–5 above,
plus a staging environment. A staging environment turns
`verify-deployment.sh` and `smoke-test.py` from operator tools into CI gates
(#39) and lets the SMS gateway run in `dry_run` against production-shaped
configuration before a farmer's phone is involved.

**Phase 2 — The first load test (1 week).** The proof dataset is one small
dairy (#29). Seed a year of a realistic one, then measure: consumer lag under
sustained collection, the outbox scan, projection rebuild time, and the
reporting queries. This is where H-4 and H-5 stop being theoretical, and where
the numbers to size the pilot host come from.

**Phase 3 — Data lifecycle (2–3 weeks).** Retention and partitioning for the
event log and consumer ledger; a tenant-deletion path; the archival policy.
Design before the pilot's data grows; execute after.

**Phase 4 — Frontend development.** This is the right sequencing. The API is
stable, published, bounded and idempotent, with a documented error contract —
which is exactly what a frontend needs to be built against without churn.
Frontend work does not depend on Phases 1–3 and can start in parallel with
Phase 1.

**Phase 5 — Commercial readiness (Phase C in the existing plan).**
Onboarding, licensing, billing and litre metering, trial management, support
runbooks. Unchanged from QR-0006.

Deferred deliberately: the Formula/Bonus/Penalty/Tax pricing engines, the
Processing and Inventory platforms, and the AI layer. None is needed for a
procurement pilot and each would widen the surface under test.

---

## 11. Recommendation — Is the backend feature complete?

**NO.**

The *procurement domain* is feature complete, and that distinction is the whole
answer. Collection → pricing → settlement → payment → receipt → notification
runs end to end, online and offline, and is proven by an E2E test and by a
seeded real dairy on real PostgreSQL. If the question were "is the procurement
business logic done", the answer would be yes without qualification.

But three things a paying customer's first thirty days will actually exercise
do not exist in executable form, and they are features rather than hardening:

1. **No transport for email.** SMS is real since MSG-001; email has no adapter
   at all. Until this review it also reported success while sending nothing.
2. **No printable receipt.** RCP-001 ships a PDF renderer that announces
   itself as a placeholder. A dairy that hands farmers proof of payment cannot
   do so.
3. **No way for a tenant's data to leave the platform.** No retention, no
   archival, no deletion. A customer can be onboarded but not offboarded.

Freezing the backend now would freeze those three out, and each becomes harder
once real data exists. They are small — an SMTP adapter, a PDF engine
registration, and a retention design — but they are not zero, and calling the
backend complete while they are open would be the kind of green-looking
statement this platform has spent four work orders learning to distrust.

**What would make it YES:** the three items above, plus freeze checklist items
1–5. That is a matter of weeks, not months.

**On the Definition of Done for this review** — *am I personally comfortable
recommending this backend for production pilot deployment?*

**Yes, conditionally, and the conditions are narrow.** The code is sound; I
executed the parts that would cost money if they were not. I would put this
platform in front of one pilot dairy the day items 1–5 of §9 are complete,
with the pilot explicitly attended: someone watching the alerts, a rehearsed
rollback, and off-host backups verified before the first collection. I would
not deploy it unattended, and I would not deploy it at all until the deployment
path has been executed once by someone who is not the pilot customer.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-08 | Engineering | ARCH-FINAL-001: final architecture review before v1.0 freeze. Two Critical operational items, six High (four fixed in-flight), seven Medium. Payment lock-ordering deadlock found and fixed; the double-payment guarantee moved from a source grep to an executed proof with a failing control; three fail-silent production defaults refused at startup. |
