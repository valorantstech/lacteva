---
id: LACTEVA-P1-SCALE-RACE-001
title: Large Imports and the Two-Operator Capture Race
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-26
last-updated: 2026-08-26
related: [LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-P1-PORTAL-SCALE-001, LACTEVA-P1-E2E-404-INVESTIGATION, LACTEVA-MASTER-PRODUCT-ROADMAP]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Large Imports and the Two-Operator Capture Race (P1-SCALE-RACE-001)

## 1. Executive summary

Two items, both named by the P0-PRODUCT-008 audit and carried forward by
P1-PORTAL-SCALE-001 §K. They turned out to be different kinds of problem, and
saying which is most of the value here.

**S-1 — large imports: a real product defect, fixed.** The platform refuses
more than 500 rows in one request (`MAX_IMPORT_ROWS`), and the portal sent the
whole file regardless. A dairy's actual 2,000-farmer spreadsheet was refused
outright — the feature failed on precisely the file it exists for. The portal
now sends the file in batches the platform accepts, renumbers the receipt to
the operator's own file, and reports exactly where a failed run stopped.

**S-2 — the two-operator capture race: no defect, a missing proof, now
written.** `next_document_number` locks the counter row `FOR UPDATE`, and
**`FOR UPDATE` is a no-op on SQLite** — so the guarantee protecting every
parchi number in the platform had never been evaluated on the engine that
implements it. It is now, on real PostgreSQL, and the platform is correct: ten
concurrent captures consume exactly ten numbers, with none duplicated and none
skipped. The proof was **watched failing** with the lock removed, where it
reproduces the precise failure the code's own comment predicts.

**Verdict: GREEN.**

## 2. Scope, and where it came from

P1-SCALE-RACE-001 was never specified — it is named three times in the
repository as a recommendation and nowhere as a work order. Scope was therefore
taken from the evidence rather than invented:

> large-import chunking (`MAX_IMPORT_ROWS=500`) and concurrent-capture race →
> **P1-SCALE-RACE-001** — `LACTEVA-P1-PORTAL-SCALE-001.md` §K

> large imports (`MAX_IMPORT_ROWS = 500`, portal does no chunking — a real
> 2,000-farmer CSV fails outright); no two-operator collection race test
> — `LACTEVA-P0-PRODUCT-008` §11, ranked **P1**

Nothing else was taken on. No UI redesign, no design system, no roadmap
capability, no backend behaviour change.

## 3. S-1 — Large imports

### The defect

`importSuppliers(rows)` / `importCustomers(rows)` posted every parsed row in
one request. The server's contract is at most `MAX_IMPORT_ROWS = 500` per
call — a real limit and a sensible one, since an import is a write per row
inside one transaction. Over that, the whole file is refused with
`import limited to 500 rows` and nothing is imported.

### The fix

`importInChunks()` in `src/lib/api.ts`, used by `CsvImport`. Three decisions,
each of which could reasonably have gone the other way:

**Sequential, not parallel.** An import is the heaviest write the portal makes.
Four concurrent batches would multiply that load on a dairy's single server to
save an operator a few seconds they are not watching.

**Renumbered to the operator's file.** The platform numbers rows within the
batch it was handed, so row 1 of batch two also comes back as "row 1". The
receipt is read by someone with the spreadsheet open, so every row is
renumbered to its own file line. (It was also a latent rendering bug: the
result list keys on `row`, and unrenumbered batches collide.)

**Nothing is retried.** The portal sends no idempotency key, so a batch that
failed in transit may or may not have been applied, and resending it could
create every farmer in it twice. Duplicated farmers are worse than a stopped
import: one is visible and fixable, the other is silent and becomes a payment.
A failure therefore stops the run and reports the boundary — rows before it are
committed and listed, rows after it were never sent — and the operator acts on
that with the file in front of them.

The operator is told this before sending ("this goes to the platform in 4
batches of up to 500, one after another"), and during ("Importing 1,000 of
2,000…").

### What was deliberately not done

No client-side retry, no partial-batch resume UI, and no change to the server's
500-row limit. Raising the cap would move the same problem to a bigger file and
put a longer transaction in front of a dairy's database.

## 4. S-2 — The two-operator capture race

### The question

Two operators, two farmers, two captures, at the same instant — one tenant
counter. `complete()` mints the parchi number through `next_document_number`,
which is a read-modify-write over `document_sequence`:

```python
statement = select(DocumentSequence).where(...).with_for_update()
```

The lock is there for exactly this reason, and the code says so. But
`with_for_update()` is a PostgreSQL lock and a **no-op on SQLite**, which is
where the entire backend suite runs. Per the repository's own standard, a
PostgreSQL guarantee tested only on SQLite is untested.

### What already existed, and why it was not this

Two neighbouring proofs cover adjacent races, and neither covers this one:

| Existing | Race it covers |
|---|---|
| `test_concurrent_accept_only_one_wins` (SQLite) | Two accepts of the **same** transaction — CAS |
| `test_collection_slip_postgres.py` | Two readers minting for the **same** transaction — must converge on ONE number |

The uncovered case is the opposite: two operators with **different**
transactions must get **two** numbers, and the series must account for exactly
what it handed out.

### The proof

`tests/test_concurrent_capture_postgres.py`, on real PostgreSQL:

1. **Two operators completing at once get different numbers** — the audit's gap
   stated as a test.
2. **Ten concurrent captures consume exactly ten numbers** — no duplicates *and
   no gaps*. A duplicate is the failure that hurts (the `uq_milk_tx_slip`
   UNIQUE constraint turns it into a 500 at the counter, on the document a
   farmer is owed). A gap is the quieter one: the series is a document trail a
   dairy is audited on, and a missing number invites the question of what was
   deleted. The counter is asserted to land at exactly 11.
3. **Two dairies capturing at once keep separate series** — the counter is per
   tenant, so the lock must be too; otherwise the second dairy's first parchi
   of the year starts at 000003.

### Result: the platform is correct

All three pass. **No product defect was found, and none was manufactured.**

### The proof can refuse

Removing `.with_for_update()` and re-running reproduces exactly the failure the
code comment predicts:

```
IntegrityError: duplicate key value violates unique constraint
[SQL: UPDATE milk_collection_transaction SET slip_number=$1 ...]
[parameters: ('SLP-2026-000002', ...)]
```

Two captures both minted `SLP-2026-000002`. Worth recording precisely: the
**two**-operator test did not fail — the narrow race rarely collides on timing.
Only the ten-way test caught it. A two-operator-only proof would have been
green and worthless, which is the argument for the fan-out.

The lock was restored immediately; `git diff` on `document_numbers.py` is empty.

### Registered, not just written

`infra/ci/postgres-proof.sh` names its suites explicitly, and
`test_no_postgres_only_suite_is_left_out_of_the_proof` fails when a
`*_postgres.py` file is not named — "a suite the proof never names is a proof
that never runs". The new suite was added to the proof and the guard passes.
That guard caught this omission before a human would have.

## 5. Security

Nothing in this milestone touches RLS, tenancy, authorization, idempotency or
money. The capture proof *strengthens* the tenancy evidence: test 3 shows two
tenants' document series remain independent under concurrent allocation, and
every session in it binds its own tenant.

## 6. Test results

| Suite | Passed | Failed | Skipped | Exit |
|---|---|---|---|---|
| Backend pytest (full, SQLite) | see §Results | 0 | PostgreSQL-gated by design | **0** |
| `test_concurrent_capture_postgres.py` (real PostgreSQL) | **3** | 0 | 0 | **0** |
| PostgreSQL proof (`verify-postgres.sh`, incl. the new suite) | all | 0 | — | **0** |
| Portal vitest | **374** (367 + 7 new) | 0 | 0 | **0** |
| Portal eslint `--max-warnings 0` | clean | — | — | **0** |
| Portal `npm run build` | success | — | — | **0** |
| Docs validation + xref | pass | — | — | **0** |

`npx tsc --noEmit` reports 5 pre-existing errors in `import-pages.test.tsx`,
identical at HEAD and untouched here; the repository's portal gate is eslint +
build, both clean.

## 7. Remaining open

- **Write latency under load has still not been profiled** (carried from
  P1-E2E-404-001 §20, where the commit moved onto the request's critical path).
  This milestone measured correctness under concurrency, not throughput.
  **TO CONFIRM.**
- The import path has no server-side resume: a stopped run is resumed by
  importing the remaining lines. Adequate, and deliberately not built into UI
  state that could disagree with the platform.
- Idempotency keys on portal writes would make a failed batch safely
  retryable. That is a portal-wide contract change, not an import fix, and
  belongs in its own work order.

## 8. Roadmap preservation

Confirmed untouched and unimplemented: AI/anomaly detection/forecasting,
advanced analytics, SAP/ERP, enterprise SSO, global identity, federation,
org-to-org, GPS, hardware scale/analyzer connectors, QR, PDF, messaging
providers, chilling centre, BMC, plant/processing, procurement transport,
farmer app, customer/outlet portal, advances/loans, payment gateway. No UI
redesign, design system, colour, typography, navigation or animation work. No
demo data or placeholder integration.

## 9. Verdict

**GREEN.** One real defect fixed at the layer that had it, one missing proof
written and registered, both guarded by tests watched failing first, and no
defect invented where the platform turned out to be right.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-26 | Engineering | Large-import chunking in the portal (`importInChunks`, sequential, receipt renumbered to the operator's file, no retry because the portal sends no idempotency key, honest stop boundary) fixing the 2,000-farmer CSV refused outright by `MAX_IMPORT_ROWS`; and the two-operator capture race proven on real PostgreSQL (`test_concurrent_capture_postgres.py` — distinct numbers, exactly ten consumed by ten concurrent captures, per-tenant series independence), registered in `postgres-proof.sh`. No product defect found in the race; the lock was already correct, and the proof was watched reproducing a duplicate `SLP-2026-000002` with it removed (P1-SCALE-RACE-001). |
