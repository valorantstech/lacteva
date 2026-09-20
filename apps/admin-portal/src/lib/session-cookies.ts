/**
 * The two session cookies, named once (WO-79 · LACTEVA-ADMIN-023).
 *
 * `lib/server/backend.ts` is `server-only` and reads `next/headers`, which
 * the front door (`src/proxy.ts`, edge runtime) cannot import — so the proxy
 * used to redeclare the access cookie's name as a local "kept in step" with
 * the server module, and it never learned the refresh cookie existed. Two
 * declarations of one fact is how WO-73 could give the portal a fourteen-day
 * refresh cookie the front door did not recognise. This module has no
 * imports at all, so both runtimes take the names from here and cannot drift.
 */

/** Set by `POST /api/auth/login`; lives as long as the access token (900 s). */
export const ACCESS_COOKIE = "lacteva_session";

/** The sliding thirty-day half of the session (D-26); spent, never read, by the browser. */
export const REFRESH_COOKIE = "lacteva_refresh";
