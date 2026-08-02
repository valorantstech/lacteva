---
id: DEVELOPMENT
title: Developing on the Lacteva Platform
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# Developing on Lacteva

How to work on this codebase. Getting it *running* is [RUNNING.md](RUNNING.md); what to build next is [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md); what the architecture *is* — [ARCHITECTURE_BASELINE_V1.md](ARCHITECTURE_BASELINE_V1.md).

## Repository Shape

```
services/platform-core/   backend (FastAPI modular monolith) — see its README for layout
apps/admin-portal/        Next.js 16 + TypeScript + Tailwind + shadcn/ui (Base UI)
apps/mobile/              Flutter 3.38+
docs/                     the knowledge base (indexes: docs/INDEX.md, docs/NAVIGATION.md)
tools/                    docs validator + xref generator (CI gates)
```

## Backend Loop

```bash
cd services/platform-core
uv sync                          # or: python3 -m venv .venv && .venv/bin/pip install -e . --group dev
make backend                     # infra + uvicorn --reload (from repo root)
uv run pytest                    # 18 tests, no infrastructure needed (SQLite + in-memory bus)
uv run ruff check . && uv run ruff format .
```

Rules that keep the codebase coherent (details in the service README):

- **New endpoint** → router in `api/routes.py`, service injected via `api/deps.py`, guarded with `require_permission("<key>")`; the key MUST exist in `modules/authz/permissions.py` first.
- **New table** → model in the owning module, then `make migration m="..."` + `make migrate`; never edit an applied migration.
- **State change** → `AuditService.record(...)` in the same transaction, and a domain event via the bus when the fact matters beyond the module.
- **Errors** → raise `core.errors` types; new user-facing strings go into `core/i18n.py` catalogs (all supported locales).
- **Incomplete edges** → `TODO(M#)` with an explanation, keyed to roadmap milestones. `grep -rn "TODO(M" services/` is the debt inventory.

## Admin Portal Loop

```bash
cd apps/admin-portal
npm install && npm run dev       # http://localhost:3000
npm run build && npx eslint src  # the CI gates
```

Notes: Next.js 16 — read `node_modules/next/dist/docs/` before assuming older conventions (e.g. `params` is now async in server components). shadcn/ui here wraps **Base UI**, not Radix: there is no `asChild`; compose via `render` or plain elements. Backend URL comes from `NEXT_PUBLIC_API_URL` (`.env.example`). API types: generate from `/openapi.json` when the typed client lands (M2) — never hand-write them.

## Mobile Loop

```bash
cd apps/mobile
flutter run --dart-define=LACTEVA_API_URL=http://10.0.2.2:8000
flutter analyze && flutter test
```

Constraints fixed before feature work (from the Collect product package): offline-first sync engine and ARB-based localization land in M2 — don't build features that assume connectivity.

## Quality Gates

Local: `pre-commit install` once (runs ruff + docs validators on commit). CI (`.github/workflows/ci.yml`) runs on every push/PR: docs validation, XREF freshness, backend lint + tests + migration check, portal build + lint, Flutter analyze + tests, and a Docker image build on `main`.

Documentation changes follow the repo's own rules: `make docs-validate` before committing; new documents start from templates ([docs/02-templates](docs/02-templates/README.md)) and carry `baseline: ARCH-BASELINE-V1` front matter.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Engineering | Initial version (SPRINT-001). |
