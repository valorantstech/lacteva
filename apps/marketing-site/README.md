# marketing-site

Lacteva public marketing website — Next.js 16 (App Router, TypeScript,
Tailwind CSS 4, shadcn/ui on Base UI). Public and unauthenticated; the
authenticated product lives in `apps/admin-portal`, and the two share a link
("Sign in"), never a UI.

## Run

```bash
npm install
npm run dev        # http://localhost:3100
```

## Quality gates (CI-enforced)

```bash
npx tsc --noEmit
npm run build
npx eslint src --max-warnings 0
npm test
```

## Conventions

- **Next.js 16**: conventions differ from older versions — consult
  `node_modules/next/dist/docs/`.
- **shadcn/ui wraps Base UI, not Radix**: no `asChild`; use the `render`
  prop or plain elements. Components in `src/components/ui/` are owned code
  copied from the admin portal — edit them here, don't share them (`libs/`
  is for services, and shadcn components are owned code by design).
- **Claim discipline is executable**: `src/app/claims.test.ts` fails the
  build on copy the workspace's own rules forbid (AI claims, invented
  traction, testimonials). Sources: `Master/Marketing` charter and
  `Master/Vision/Product_Principles.md`.
- **No secrets in the bundle**: the demo-request handler reads
  `LACTEVA_LEADS_WEBHOOK_URL` server-side at request time
  (`src/lib/server/leads.ts`, guarded by `server-only`). There is no
  `NEXT_PUBLIC_*` secret, so one image serves every environment.
- **Interim brand**: no brand guideline or logo exists yet
  (`Shared/Brand` and `Shared/Logos` are empty). The palette in
  `src/app/globals.css` seeds from the mobile app's `#1B5E20` green and the
  mark in `src/components/logo.tsx` is a placeholder — both are single
  swap points for when `Master/Marketing/Branding` is authored.

## Environment

See `.env.example`: `LACTEVA_LEADS_WEBHOOK_URL` (demo-request forwarding,
unset ⇒ the form degrades honestly with a 503), `NEXT_PUBLIC_PORTAL_URL`
(shows the "Sign in" link when set), `LACTEVA_SITE_URL` (canonical origin
for metadata/sitemap; defaults to a placeholder until the public domain is
decided).

## Planned next slices

- Real brand assets once `Master/Marketing/Branding` and `Logo` are authored.
- Production routing decision: this site and the admin portal both want `/`
  behind nginx — separate hostnames is the expected answer; not wired yet.
- ECR publishing: `images.yml`'s OIDC role reaches exactly two repositories,
  so shipping this image needs a `lacteva/marketing-site` ECR repository and
  a role policy change (CI already builds the Dockerfile on main).
- Localized pages (the platform already ships en/sw/hi/ar).
