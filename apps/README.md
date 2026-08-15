# apps/

Client applications of the Lacteva platform — one subfolder per app. Apps consume platform APIs only; they contain no business rules of their own (rules live in services, per the EA layer discipline).

| App | Stack | Status |
| --- | --- | --- |
| [`admin-portal/`](admin-portal/README.md) | Next.js + TypeScript + Tailwind + shadcn/ui | Scaffold pending (M2) |
| [`marketing-site/`](marketing-site/README.md) | Next.js + TypeScript + Tailwind + shadcn/ui | Built (public site; pre-launch copy) |
| [`mobile/`](mobile/README.md) | Flutter | Scaffold pending (M2) |

`marketing-site/` is the public, unauthenticated face of Lacteva;
`admin-portal/` is the authenticated business application. They are separate
deployables that share a link ("Sign in"), never a UI.
