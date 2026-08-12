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
# The build runs on the same small instance that serves the platform, and it
# failed with `spawn ENOMEM` once the app grew past ~30 routes: Next.js fans
# static generation out to one worker per CPU, and each worker is a full Node
# heap. Capping the heap and the worker count keeps the build inside the
# memory the box actually has — which is cheaper, and more honest, than
# resizing the instance to accommodate a build that does not need the room.
ENV NODE_OPTIONS=--max-old-space-size=1536
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
