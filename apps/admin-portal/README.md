# admin-portal

Lacteva administration portal — Next.js 16 (App Router, TypeScript, Tailwind CSS 4, shadcn/ui on Base UI). Currently ships the SPRINT-001 bootstrap: a live platform-status dashboard polling `platform-core`'s readiness endpoint, with links to OpenAPI and metrics.

## Run

```bash
npm install
npm run dev            # http://localhost:3000
# or from the repo root: make portal   (containerized: part of `make dev`)
```

Backend URL via `NEXT_PUBLIC_API_URL` (see `.env.example`; defaults to `http://localhost:8000`).

## Quality gates (CI-enforced)

```bash
npm run build
npx eslint src --max-warnings 0
```

## Conventions

- **Next.js 16**: conventions differ from older versions — consult `node_modules/next/dist/docs/` (notably: `params` is async in server components; strict `react-hooks/set-state-in-effect` lint).
- **shadcn/ui wraps Base UI, not Radix**: no `asChild`; use the `render` prop or plain elements. Components live in `src/components/ui/` and are owned code — edit them.
- **API types**: to be generated from platform-core's `/openapi.json` (roadmap M2) — never hand-written.

## Planned next slices (M2, per DEVELOPMENT_ROADMAP.md)

Auth (login via `POST /v1/auth/token`, session refresh, permission-aware nav from `/v1/auth/me`) → organizations → roles & assignments (rendering the permission registry) → configuration editor → audit browser.
