# Lacteva admin portal — production image (PORTAL-001 / F-03)
# Build:  docker build -t lacteva/admin-portal apps/admin-portal
# Run:    docker run -p 3000:3000 -e LACTEVA_API_URL=http://api:8000 lacteva/admin-portal
#
# Deliberately the same shape as services/platform-core/Dockerfile: multi-stage,
# non-root, health-checked. One deployment architecture, not two.
#
# NOTHING SECRET IS BUILT IN. The portal reads `LACTEVA_API_URL` from the
# environment at REQUEST time (see src/lib/server/backend.ts). There is no
# `NEXT_PUBLIC_*` build argument, so the same image runs in staging and in
# production, and no value baked into this image ever reaches a browser.

FROM node:22-bookworm-slim AS deps
WORKDIR /app
# Dependencies first so a source change does not re-resolve the tree.
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# DEMO-009: building on the same small instance that serves the platform failed
# with `spawn ENOMEM` once the app grew past ~30 routes.
#
# The cause was not heap exhaustion — it was `fork()` being REFUSED. That host
# runs `vm.overcommit_memory=2` (strict accounting), under which forking a
# worker requires commit charge equal to the parent's reservation. A parent
# holding a 1536MB heap therefore cannot spawn one even with ~2GB free, and
# raising the cap made it worse rather than better. So the default here is
# deliberately SMALL, and `experimental.cpus` in next.config.ts keeps the
# number of workers down.
#
# DEMO-010 moved the build to GitHub Actions (.github/workflows/images.yml),
# which has 16GB and no strict overcommit — so it passes 4096 and the build is
# no longer squeezed. The small DEFAULT stays because it is what makes an
# emergency build ON the host still possible.
ARG NODE_HEAP_MB=768
ENV NODE_OPTIONS=--max-old-space-size=${NODE_HEAP_MB}
RUN npm run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
# Never run as root in production. `node` already exists in this image.
RUN mkdir -p /app && chown node:node /app
# `output: "standalone"` emits a server with only the modules it imports, so
# there is no node_modules layer here at all.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3000
# Hits the portal's own liveness route, not the platform's — this check must
# answer "is the portal up", not "is the API up". Conflating them makes a
# backend outage restart a healthy frontend.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
    CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
