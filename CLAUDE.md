# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Lacteva is the flagship product of Phoenix Software**, an enterprise dairy
platform. This repository holds the code and the governed documentation.

## Read these first

1. **[STD-0007 — Phoenix Software Engineering Standard](docs/00-standards/STD-0007-phoenix-software-engineering-standard.md)**
   — a permanent, binding directive. Fifteen engineering principles and a
   six-dimension Definition of Done. It governs code, tests and operations,
   and it outranks an in-flight work order on *how* work is done.
2. **[docs/ai/CLAUDE_CONTEXT.md](docs/ai/CLAUDE_CONTEXT.md)** — the permanent
   onboarding guide: architecture, module map, coding standards, what NOT to
   do, and the honest divergence register.
3. **[ARCHITECTURE_BASELINE_V1.md](ARCHITECTURE_BASELINE_V1.md)** — locked.
   Wins over everything on *what the architecture is*.
4. **[CHANGELOG.md](CHANGELOG.md)** — what already exists, newest first. Read
   before building anything; most "new" work has a nearest neighbour already
   in the tree, and imitating it is the house style.

## The rule that matters most here

**Every production guarantee must be executable. Documentation alone is
insufficient.**

This is not a slogan. Four work orders did nothing but *execute* guarantees
that were already written, reviewed and CI-wired, and found **fourteen
defects** — including that the platform could not serve a single request on
PostgreSQL, that every row-level security policy was inert, that backups
aborted on any real deployment, and that point-in-time recovery did not
exist. None was findable by reading.

So: **a PostgreSQL guarantee tested only on SQLite is untested.** A skipped
proof is worse than an absent one, because it is green. A proof must show the
guard can *refuse*, not merely that it is present.

## Commands

Backend (`services/platform-core`) — **`uv` is not installed locally**, so use
the checked-in venv. CI runs the same commands via `uv run`.

```bash
cd services/platform-core
.venv/bin/python -m pytest tests/ -q                  # full suite (~10–15 min — background it)
.venv/bin/python -m pytest tests/test_pricing_matrix.py -q          # one file
.venv/bin/python -m pytest tests/test_payments.py::test_name -q     # one test
.venv/bin/python -m pytest -k "settlement and not e2e" -q           # by expression
.venv/bin/ruff check . && .venv/bin/ruff format --check .           # lint gate
.venv/bin/ruff check . --fix && .venv/bin/ruff format .             # autofix
LACTEVA_DATABASE_URL=sqlite+aiosqlite:///./scratch.db \
  .venv/bin/alembic upgrade head                     # migrations; verify up→down→up
```

Tests need **no infrastructure**: `conftest.py` pins in-memory SQLite, the
in-memory bus and inline outbox before any import.

PostgreSQL-only suites (`test_rls_postgres.py`, `test_exact_aggregation_postgres.py`,
`test_disaster_recovery_postgres.py`) skip silently without a database, which is
correct on a laptop and a **failure** in a pipeline — hence two switches in
`tests/postgres_support.py`:

```bash
LACTEVA_TEST_POSTGRES_URL=postgresql+asyncpg://…  # makes them run
LACTEVA_REQUIRE_POSTGRES=1                        # makes a missing URL a collection ERROR
```

The four proofs — all run with no Docker and no root, because real PostgreSQL
comes from the `pgserver` wheel:

```bash
./infra/ci/verify-postgres.sh    # migrations from empty, RLS, backup, restore
./infra/ci/dr-proof.sh           # recovery into a separate instance
./infra/ci/pitr-proof.sh         # point-in-time recovery, 4 targets
./infra/ci/postgres-proof.sh     # the nine-step CI proof (KEEP_DATABASES=1 to inspect)
```

Clients and docs:

```bash
cd apps/admin-portal && npm run build && npx eslint src --max-warnings 0
cd apps/mobile && flutter analyze && flutter test
python3 tools/validate/validate_docs.py     # front matter, IDs, links, versions
python3 tools/xref/generate_xref.py         # add --check for freshness only
```

`make dev|infra|backend|portal|mobile` exist and are the documented entry
points, but every one of them shells out to `docker compose` — see below.

## Architecture in one page

**One deployable, many modules.** `services/platform-core` is a FastAPI
modular monolith; each folder under `src/platform_core/modules/` is a bounded
context and a future service seam. A module owns exactly one canonical concept
and is referenced elsewhere **by UUID only** — never query another module's
tables, never import its models; go through its service or consume its events.

**Dependency direction** is routes → application services → models /
infrastructure ports. Routers never open a session and never construct a
service: `api/deps.py` is the composition root (it also holds
`require_permission()`). Infrastructure sits behind ports (`EventBus`,
`ObjectStorage`, `Notifier`, hardware adapters) with real and in-memory
implementations — that pairing is why the suite needs no infrastructure.

**Module file convention:** `models.py` (persistence + constants) and
`service.py` (application service + Pydantic DTOs — `*Command`/`*Input` in,
`*View`/`*Page` out). A second service file is fine when one would be
unwieldy (`pricing/matrix.py`, `pricing/calculator.py`, `pricing/resolution.py`).
Pure domain logic lives as module-level functions, testable without I/O.

**Events go through the Relay, always.** The injected `Bus` is an
`OutboxEventBus`: publishing writes an `event_outbox` row *inside the caller's
transaction*, so rollback discards the event with the business change. Never
call `get_event_bus()` from module code, never publish after commit. Wire
names are `<domain>.<past-tense-fact>.v<major>`, mapped from domain names in a
module-level `BUS_EVENTS` dict. The receiving half reads that same durable log
with per-consumer cursors and an idempotency ledger; registered consumers run
**projections first**, because read models are inputs to other consumers.

**Tenancy is `Organization.id`.** A contextvar carries it, every query filters
by it, and PostgreSQL RLS enforces it in the database — so application filters
are defence-in-depth, and a forgotten filter returns nothing rather than
someone else's rows. Cross-tenant machinery (relay, consumers, projection
rebuilds, backup, health) must use `PlatformSessionFactory` in `core/rls.py`;
building an ordinary session there is the defect MT-001 found. Every table is
declared tenant-owned or platform-global in `core/rls.py` — a build check, not
a list to maintain by hand.

**Registries before code.** Permissions (`modules/authz/permissions.py`,
`<module>.<entity>.<action>`), business rules (`BR-NNNN` in the Business Rules
Register, cited by the enforcing code), events (`BUS_EVENTS`), models
(`core/model_registry.py`). Registry entry first, guard second, test third.

**Concurrency is CAS**, not `SELECT FOR UPDATE`: `UPDATE … WHERE status =
<expected>` with a rowcount check, because it is portable to the SQLite test
stack. The one deliberate exception is the settlement balance read, which is
locked `FOR UPDATE` (ARCH-001).

**Money is `Decimal`, end to end.** Floats are rejected by type guard;
aggregation casts to unconstrained `NUMERIC` inside the aggregate; clients send
row ids and never prices.

**Errors** come from the `core/errors.py` hierarchy and render as RFC-9457
problem+json. Another tenant's resource is a 404, never a 403.

## Things that have bitten before

- `import_all_models()` in `core/model_registry.py` is a **call**, because a
  `ruff --fix` once deleted the equivalent import block and the next
  autogenerate would have dropped every table. Do not "clean it up".
- Use `utcnow()` / `as_utc()` from `core/db.py`; anything read from SQLite
  needs `as_utc()` before comparison.
- Idempotency is a **route class**, not a router dependency — `include_router`
  preserves each child's route class, and router dependencies run before
  authentication.
- Never edit an applied migration; the chain is linear.
- Immutable means immutable: completed transactions, published rate cards,
  finalized settlements, receipts. Corrections are new versions or adjustments.

## Local environment

- **No Docker on this machine.** Compose files can only be checked
  structurally; the proofs above stand up their own PostgreSQL, and the
  `make` targets that need Compose will not run here.
- **`uv` is not installed locally** (CI uses it). Use
  `services/platform-core/.venv/bin/python` and `.venv/bin/ruff`.
- Flutter 3.38 at `/mnt/data/programfiles/flutter`; Node 22 available.
- Admin portal is **Next.js 16** with **shadcn/ui on Base UI — no `asChild`**.
- The full test suite takes ~10–15 minutes; run it in the background.

## Gates before every commit

`ruff format` + `ruff check` + full `pytest`, then
`python3 tools/validate/validate_docs.py` and
`python3 tools/xref/generate_xref.py`. Portal build + lint and
`flutter analyze` + `flutter test` when those trees changed. Update
`CHANGELOG.md` for every increment. All green, no exceptions — never "CI will
catch it", and never weaken a test to pass.

**Standing instruction:** every file-changing turn ends with a Conventional
Commit pushed to `origin main`.

## Related workspace

Business, product, UX and research material lives **outside this repository**
at `../Master/`. It is not governed and is not a source of truth — if the two
disagree, this repository wins.
