# Lacteva — engineering context

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

## Proving it — all four run with no Docker and no root

```bash
./infra/ci/verify-postgres.sh                        # migrations, RLS, backup, restore
./infra/ci/dr-proof.sh                               # recovery into a separate instance
./infra/ci/pitr-proof.sh                             # point-in-time recovery, 4 targets
cd services/platform-core && .venv/bin/python -m pytest tests/ -q
```

Real PostgreSQL comes from the `pgserver` wheel — that is why these run here
at all.

## Local environment

- **No Docker on this machine.** Compose files can only be checked
  structurally; the proofs above stand up their own PostgreSQL.
- **`uv` is not installed locally** (CI uses it). Use
  `services/platform-core/.venv/bin/python` and `.venv/bin/ruff`.
- Flutter 3.38 at `/mnt/data/programfiles/flutter`; Node 22 available.
- Admin portal is **Next.js 16** with **shadcn/ui on Base UI — no `asChild`**.
- The full test suite takes ~10–15 minutes; run it in the background.

## Gates before every commit

`ruff format` + `ruff check` + full `pytest`, then
`python3 tools/validate/validate_docs.py` and
`python3 tools/xref/generate_xref.py`. All green, no exceptions.

**Standing instruction:** every file-changing turn ends with a Conventional
Commit pushed to `origin main`.

## Related workspace

Business, product, UX and research material lives **outside this repository**
at `../Master/`. It is not governed and is not a source of truth — if the two
disagree, this repository wins.
