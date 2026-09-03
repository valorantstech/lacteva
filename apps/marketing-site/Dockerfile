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

# WO-65: WHERE THE PORTAL LIVES, BAKED IN AT BUILD TIME.
#
# `NEXT_PUBLIC_*` is INLINED into the bundle by `next build` — it is not read
# from the environment when the server starts. That is the whole defect this
# fixes: `/login` on the live site rendered "its address is not configured in
# this environment" and offered a visitor who wanted to SIGN IN a trial
# sign-up instead, and no amount of adding the variable to compose could have
# helped, because by then the build had already decided.
#
# So it is an ARG, passed by the images workflow, and the value travels with
# the image. Changing the portal's address means REBUILDING the marketing
# site — which is the honest cost of a build-time constant, and the reason
# `test_portal_url.test.ts` refuses a production build that has none.
#
# The default is empty on purpose: a local `docker build` with no argument
# gets the explanatory /login page rather than somebody else's portal.
ARG NEXT_PUBLIC_PORTAL_URL=""
ENV NEXT_PUBLIC_PORTAL_URL=${NEXT_PUBLIC_PORTAL_URL}
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
