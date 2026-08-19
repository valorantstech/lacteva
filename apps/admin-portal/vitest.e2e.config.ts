import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

/**
 * The REAL client↔server suite (P1-E2E-HARNESS-001).
 *
 * Deliberately a separate config from `vitest.config.ts`: the ordinary portal
 * suite is hermetic and mocks the network, and it must stay that way — a
 * developer running `npm test` has no platform. This one is driven by
 * `infra/e2e/run-e2e.sh`, which starts a real PostgreSQL, a real FastAPI
 * server and a synthetic dairy, then points the portal's own server code at
 * it. Node environment, not jsdom: what is under test here is the portal's
 * server boundary (its auth and proxy routes), not a rendered page.
 */
export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "server-only": resolve(__dirname, "src/test/server-only-stub.ts"),
    },
  },
  test: {
    environment: "node",
    include: ["e2e/**/*.e2e.test.ts"],
    // A real server, a real database and a real migration are involved.
    testTimeout: 30_000,
    hookTimeout: 30_000,
  },
});
