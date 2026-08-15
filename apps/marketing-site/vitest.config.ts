import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

/**
 * PORTAL-001 / F-09. The portal had zero tests: fourteen pages defended by
 * nothing but `tsc` and eslint, neither of which can tell you that sign-in
 * works.
 *
 * Vitest with jsdom, no Babel plugin — esbuild handles the JSX, which avoids
 * the `@babel/core` peer conflict in this tree and is faster anyway.
 */
export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      // See the stub's own comment: the real guard runs in `next build`.
      "server-only": resolve(__dirname, "src/test/server-only-stub.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
