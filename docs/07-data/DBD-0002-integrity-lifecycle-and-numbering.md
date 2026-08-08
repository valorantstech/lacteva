---
id: DBD-0002
title: Referential Integrity, Data Lifecycle, Document Numbering and Database Roles
type: dbd
status: Approved
version: "1.1"
owner: Engineering
created: 2026-08-08
last-updated: 2026-08-08
related: [DBD-0001, QR-0007, STD-0007]
baseline: ARCH-BASELINE-V1
---

# DBD-0002 — Referential Integrity, Data Lifecycle, Document Numbering and Database Roles

The four database decisions PROD-001 was asked to make explicitly. Each states
what was decided, what was implemented, and — where nothing was implemented —
why that is the right answer rather than an omission.

---

## 1. Referential Integrity

### 1.1 The measured position

Enumerated from `Base.metadata`, not estimated: the schema has **57 tables**,
**66 reference columns** (`*_id` other than `tenant_id`), and **6 foreign key
constraints**. So roughly 91% of references are unenforced by the database.

Every reference column was classified. The taxonomy the work order asked for:

| Class | Meaning | Count |
| --- | --- | --- |
| **A** | Must be enforced in the database | 7 |
| **B** | Application-level invariant, deliberately | 31 |
| **C** | Intentionally denormalized or not a reference at all | 22 |
| **D** | Historical / legacy | 6 |

### 1.2 Class A — enforce in the database

A reference qualifies as A when **all three** hold: it points within one
module (so a foreign key does not couple two future services), the child is
meaningless without its parent, and an orphan would corrupt money or evidence
rather than merely look untidy.

| Child | Reference | Why A |
| --- | --- | --- |
| `settlement_line` | `settlement_id` | The arithmetic behind a payable. An orphan line is money attributed to nothing. |
| `payment_line` | `payment_id` | Already an FK. Retained as the reference case. |
| `payment_attempt` | `payment_id` | Execution evidence for a payment that must exist. |
| `receipt_line` | `receipt_id` | Already an FK. |
| `pricing_matrix_row` | `matrix_id` | A price band with no matrix is an unreachable price. |
| `transaction_event` | `transaction_id` | The ordered event log of one transaction. |
| `transaction_snapshot` | `transaction_id` | One-to-one with its transaction by construction. |

**Implemented in PROD-001: none of the four missing ones.** This is a
deliberate deferral and the reason matters.

Adding a foreign key to a populated table takes an `ACCESS EXCLUSIVE` lock for
the validation scan unless it is added `NOT VALID` and validated separately.
The platform has never executed a production deployment (QR-0007 C-1), so the
first migration that takes a heavy lock would be doing so on an unrehearsed
deploy path, against a database whose real size nobody has measured. The
correct sequence is: rehearse the deployment, measure, then add the four
constraints as `NOT VALID` followed by `VALIDATE CONSTRAINT`, which takes only
a `SHARE UPDATE EXCLUSIVE` lock.

`backup/integrity.py`'s orphan detection already reports violations of all
seven, so the gap is observable in the meantime. **Recommended as the first
migration after the deployment rehearsal.**

### 1.3 Class B — application-level invariant

Every cross-module reference: `settlement.supplier_id`,
`payment.supplier_id`, `receipt.payment_id`, `milk_collection_transaction.
supplier_id`, `rate_card_center_assignment.center_id`, and 26 more.

This is the modular-monolith decision and it is not a shortcut. A foreign key
from `settlement` to `supplier` is a database-level coupling between two
modules that are explicitly intended to become separate services; adding it
would make the extraction the architecture is designed for require a schema
migration and a data move. The boundary rule (reference by id, consume events)
is what keeps them separable.

The cost is real and is accepted: these can orphan, and only
`backup/integrity.py` will say so.

### 1.4 Class C — not a reference

Twenty-two columns that look like references and are not:

* `event_outbox.correlation_id`, `causation_id`, `aggregate_id` — a
  correlation id is a trace token, and an aggregate id is polymorphic across
  every aggregate type in the platform. Neither has a single target table.
* `notification.event_id`, `event_delivery.event_id` — point into the outbox,
  which is explicitly designed to be **partitioned and detached** (DBD-0001
  §7.3). A dependent constraint would make dropping an old partition
  impossible, which is the entire retention strategy for that table.
* `sync_operation.operation_id`, `server_id`, `client_reference` —
  client-generated identifiers from a device, not platform rows.
* `supplier_profile.national_id` — a government identifier. Matched by name
  only; it is not a foreign key to anything.
* The `projection_*` tables — rebuildable read models (BR-0015). A constraint
  would make a rebuild ordering-dependent on tables it does not own.

### 1.5 Class D — historical

Six columns predating the module boundaries as they now stand
(`membership.user_id`, `user_role.user_id`, `password_reset_token.user_id`,
`operator_assignment.user_id`/`center_id`, `device.center_id`). They are
intra-platform and would qualify as A on the merits, but they are load-bearing
for authentication, and the platform has no deployment rehearsal yet. Same
sequencing as A.

---

## 2. Data Lifecycle

### 2.1 What was implemented

**Tenant offboarding, in full** — `core/tenant_lifecycle.py`, exposed at
`/v1/tenant-data/{export,offboarding-plan,offboard}`. Three treatments, because
erasure and retention are genuinely in conflict:

* **PURGE** — operational data with no retention duty. Deleted.
* **ANONYMIZE** — financial and audit records. The row survives; the identity
  in it does not.
* **RETAIN** — the tombstone, and the financial series itself.

After offboarding, "how much did this dairy pay in July 2026" is answerable and
"who was S-004821" is not. **PURGE is the default** for an unclassified table,
because a table nobody thought about is more dangerous kept than deleted.

Export is available independently and is the prerequisite an operator is
expected to run first; it is not enforced in code, because a customer entitled
to erasure is not obliged to take a copy.

### 2.2 What was deliberately NOT implemented

**No partitioning.** The work order said not to implement premature
partitioning and that is right: the platform has never run at volume, and
partitioning chosen from a model rather than from measurement is a schema
change that has to be undone. DBD-0001 §9 identifies nine candidate tables.

**No time-based retention sweep.** Deleting old rows is only safe once the
tables are partitioned (a bulk `DELETE` on `event_outbox` at volume would
bloat the table it is trying to shrink and compete with the request path).

### 2.3 The v1 strategy

| Table | Growth driver | v1 | When it becomes urgent |
| --- | --- | --- | --- |
| `event_outbox` | Every business fact | None | > 50M rows. Partition by month, detach and drop. |
| `event_delivery` | Every dispatch attempt | None | With the outbox. Deliberately has no `tenant_id` so partitions detach cleanly. |
| `consumer_execution` | consumers × events | None | **First to hurt.** One row per consumer per event, forever. |
| `audit_record` | Every mutation | Anonymized on offboarding | Retain 7 years, then partition-drop. |
| `milk_collection_transaction` | 2 collections/supplier/day | Retained | ~100M rows at the modelled scale. |
| `transaction_event` / `_metrics` / `_snapshot` | Per transaction | Retained | With the parent. |
| `idempotency_record` | Per mutating request | **Swept at 24h** — the only lifecycle that exists today | Already handled. |
| `projection_*` | Rebuildable | Truncate and rebuild (BR-0015) | Never — not a retention problem. |
| `notification` | Per message | Anonymized on offboarding | Retain 2 years. |

**Order of work:** measure at volume → partition `event_outbox`,
`event_delivery` and `consumer_execution` → retention sweep on the partitions
→ everything else. The consumer ledger is first because it grows fastest and is
the one nothing else compensates for.

---

## 3. Financial Document Numbering

### 3.1 The decision

**Random 24-bit hex is not acceptable for financial documents. Replaced with a
per-tenant, per-type, per-year monotonic sequence.**

    STL-2026-000001    PAY-2026-000001    RCP-2026-000001

Two independent reasons, either sufficient:

1. **Legal.** Kenya's eTIMS, India's GST invoicing rules and the EU VAT
   directive all require a **sequential series** on invoices and receipts. A
   random string satisfies none of them, and renumbering documents a pilot has
   already issued to farmers is materially harder than choosing correctly now.
2. **Correctness.** The previous allocation was a check-then-act loop —
   generate, `SELECT` to see if it is free, retry five times. Two transactions
   can generate the same candidate, both see it free, and one fails on the
   unique constraint with a 500. Collision probability grows with the square of
   the document count, so it degrades precisely as a customer succeeds.

### 3.2 What "gapless" honestly means

The series is **monotonic and unique**, and gapless in the ordinary case. It is
**not** gapless under rollback: a transaction that allocates 42 and then fails
leaves 42 unused. Preventing that would mean holding the counter lock until
commit across every allocator, serialising the whole platform behind one row.

That trade is the standard one. Where a jurisdiction demands strict
gaplessness, accepted practice is a reconciliation register recording
issued-and-voided numbers rather than preventing gaps — future work, not built
speculatively.

### 3.3 Why a table rather than a PostgreSQL SEQUENCE

A native sequence is per-database, so every dairy would share one series and
each could infer the others' volumes from the gaps in its own numbers. It also
cannot reset per year. Sequences are non-transactional anyway, which buys
nothing once rollback gaps are accepted.

### 3.4 Migration position

Documents issued before this change keep their random numbers. They are
already immutable, and rewriting an issued receipt's number would be worse than
a discontinuity in the series. The series simply starts at 1 for each tenant.

---

## 3b. Money Storage — `unit_price` (DEPLOY-001)

`pricing_matrix_row.unit_price` was `double precision`. BR-0005 made all
*arithmetic* exact via `Decimal(str(x))`, but exact arithmetic on an inexact
input is still inexact: the price was already approximate before the first
multiplication, and it is the number every calculation, settlement, payment and
receipt descends from.

Now `NUMERIC(12, 4)`, matching `milk_collection_transaction.unit_price` — the
house standard since PRC-004, and the column this value is copied into.

**Why the cast is safe, established by executing it first.** PostgreSQL casts
`float8` to `numeric` through the float's SHORTEST round-trip text
representation, not its binary expansion, so `44.7291` converts to exactly
`44.7291` and not `44.729100000000002`. That property is what makes this a
storage fix rather than a data-correction exercise.

**Why the migration still refuses to run blind.** The same experiment showed
what the cast does not preserve: `44.72915 → 44.7292`, `0.00005 → 0.0001`,
`0.00001 → 0.0000` (which also violates `ck_matrix_row_price`). A price with
more than four decimals would be silently changed, so the migration **counts
those rows first and aborts naming them**.

**Verified before and after against a real database**, not inferred: nine
representative prices written as `float8`, migrated, and compared row by row —
all identical; the `up → down → up` round trip preserves every value; and a
deliberately-planted five-decimal price aborts the migration and leaves the
column untouched.

**Contract change.** `unit_price` now serialises as a **string** in API
responses, like every other money field (`payment.amount`,
`settlement.net_amount`). Requests may still send a JSON number — Pydantic
parses it into `Decimal` via its string form. The admin portal and the Flutter
client were updated; a client that read it as a number needs the same change.

`from_value`/`to_value` remain `FLOAT` deliberately: they are band BOUNDARIES
compared against a quality reading, not money, and converting them changes
which band a boundary-valued reading selects — a behavioural change to BR-0004
that needs its own analysis.

## 4. Database Roles

### 4.1 The rule

**Production must never connect as a superuser, the schema owner, or on a
development credential.** This is not hygiene — a PostgreSQL superuser
**ignores every row-level security policy**, including `FORCE`. VER-001 found
exactly this: the production stack connected as `${POSTGRES_USER}`, which the
official image creates as a superuser, so every policy SEC-001, SEC-002 and
MT-001 built was inert while remaining visible in `pg_policies`.

### 4.2 The role model

| Role | Owns | Used by | Privileges |
| --- | --- | --- | --- |
| `postgres` (or a named owner) | The schema | Migrations only, run as a one-shot job | DDL |
| `lacteva_app` | Nothing | **The application** | `CONNECT`, `USAGE` on schema, DML on all tables and sequences. **`NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`** |
| `lacteva_backup` | Nothing | `pg_dump` / physical backup | `CONNECT`, read-only |

Migrations run as the owner because DDL requires it; the application never
performs DDL at runtime, so it needs none. Separating them is what makes the
isolation assertions meaningful — a role that can
`ALTER TABLE … DISABLE ROW LEVEL SECURITY` is not a role whose confinement
proves anything.

### 4.3 How it is enforced, at three levels

1. **Configuration.** `Settings._refuse_dev_secrets_in_prod` refuses a
   `database_url` that is not PostgreSQL or that carries `lacteva:lacteva` /
   `postgres:postgres` credentials. The process does not start.
2. **Runtime.** `assert_rls_is_enforceable()` queries `pg_roles` at startup and
   **raises** in `prod`/`staging` when the connected role is `SUPERUSER` or has
   `BYPASSRLS`. Also enforced by refusing `LACTEVA_RLS_ENABLED=false` in prod,
   which would otherwise disable the boundary *and* this check together.
3. **Verification.** `infra/ci/postgres-proof.sh` creates `lacteva_app` with
   `NOSUPERUSER NOBYPASSRLS` and **asserts it before running any isolation
   test**, so a misconfigured pipeline cannot pass those tests vacuously.

### 4.4 The pooler constraint

RLS binds the tenant with `SET LOCAL`, which is transaction-scoped. **PgBouncer
must run in `transaction` mode.** In `statement` mode a pooled connection can
serve a query with another request's tenant binding. This is a deployment rule,
not a preference.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-08 | Engineering | DEPLOY-001: `pricing_matrix_row.unit_price` migrated FLOAT → NUMERIC(12,4) with a pre-flight guard that refuses to round any price, verified before/after against PostgreSQL 16.2 including the rollback round trip. §3b added. |
| 1.0 | 2026-08-08 | Engineering | PROD-001: referential integrity classified (7 A / 31 B / 22 C / 6 D, enforcement deferred behind the deployment rehearsal with a stated reason); v1 data lifecycle strategy with tenant offboarding implemented and partitioning deliberately deferred; financial document numbering moved from random 24-bit hex to per-tenant sequential series; application database role model documented and enforced at three levels. |
