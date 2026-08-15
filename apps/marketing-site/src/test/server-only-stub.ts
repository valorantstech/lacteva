/**
 * `server-only` is a build-time guard: importing it from a client bundle is a
 * compile error, which is exactly what should happen to `lib/server/backend`.
 * Under Vitest there is no client bundle to guard, so the import is stubbed.
 * The guard still does its job in `next build`, which runs in CI.
 */
export {};
