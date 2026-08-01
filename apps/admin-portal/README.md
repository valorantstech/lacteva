# admin-portal

Next.js administration portal for platform and tenant administrators: organization management, roles/permissions, configuration, and audit views — driven entirely by the platform-core API and its permission registry.

**Status: scaffold pending (roadmap M2).** The scaffold is intentionally not hand-written — generate it with the official tooling so lockfiles and config are authentic:

```bash
cd apps/admin-portal
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --use-npm
npx shadcn@latest init
```

Planned first slices (each maps to platform-core endpoints that already exist):

1. Auth: login against `POST /v1/auth/token`, session via refresh flow; permission-aware navigation from `GET /v1/auth/me`.
2. Organizations: list/create (`/v1/organizations`, requires `organization.manage`).
3. Roles & assignments: `GET /v1/authz/permissions` renders the registry; role builder posts to `/v1/authz/roles`.
4. Configuration editor: `/v1/config/{key}` with scope selection.
5. Audit browser: `/v1/audit`.

TODO(M2): generate a typed API client from platform-core's `/openapi.json` (openapi-typescript) — never hand-write API types.
