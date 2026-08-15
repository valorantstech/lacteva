# Lacteva marketing site — production image
# Build:  docker build -t lacteva/marketing-site apps/marketing-site
# Run:    docker run -p 3100:3100 lacteva/marketing-site
#
# Deliberately the same shape as apps/admin-portal/Dockerfile: multi-stage,
# non-root, health-checked. One deployment architecture, not two.
#
# NOTHING SECRET IS BUILT IN. The demo-request handler reads
# `LACTEVA_LEADS_WEBHOOK_URL` from the environment at REQUEST time (see
# src/lib/server/leads.ts). No secret ever enters this image or a browser.

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
# Same memory discipline as the admin portal (see its Dockerfile for the
# strict-overcommit story). Small default keeps an emergency build on the
# serving host possible; CI passes a bigger value via NODE_HEAP_MB.
ARG NODE_HEAP_MB=768
ENV NODE_OPTIONS=--max-old-space-size=${NODE_HEAP_MB}
RUN npm run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3100 HOSTNAME=0.0.0.0
# Never run as root in production. `node` already exists in this image.
RUN mkdir -p /app && chown node:node /app
# `output: "standalone"` emits a server with only the modules it imports, so
# there is no node_modules layer here at all.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3100
# Answers "is the marketing site up", nothing else — there is no backend to
# conflate it with.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
    CMD node -e "fetch('http://127.0.0.1:3100/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
