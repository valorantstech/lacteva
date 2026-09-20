import "server-only";

import { cookies } from "next/headers";

import { ACCESS_COOKIE, REFRESH_COOKIE, backendUrl, cookieOptions } from "@/lib/server/backend";

/**
 * Spend the refresh cookie (WO-73 — the portal-side twin of WO-69).
 *
 * The platform issues a 900-second access token and a refresh token that
 * lives thirty days from its last use (D-26; fourteen when this was written).
 * The login route stored both and nothing ever spent the second: on
 * a 401 the proxy ended the session, so an administrator finalising
 * settlements was ejected every quarter of an hour — and this defect ended
 * its own discoverer's session mid-verification.
 *
 * The properties below are the ones `4d1077e` established on the handset,
 * and each is here because it is a way this goes wrong:
 *
 *  * **Single-flight, and it is not optional here.** The platform ROTATES
 *    refresh tokens and treats reuse of a rotated one as a theft signal — it
 *    revokes the whole session. A dashboard opening with six requests meets
 *    six 401s at once; six refreshes with the same cookie would have the
 *    second one KILL the session the first just renewed. So every request
 *    carrying the same refresh token awaits the same exchange, and the
 *    result is remembered briefly so a request that arrives after the
 *    exchange, still carrying the old cookie the browser had at the time,
 *    gets the new pair rather than a reuse-revocation.
 *  * **Replay the original request** with the new token — the caller does.
 *  * **Sign out only when the refresh is REFUSED.** An expired access token
 *    is not a security event; a 4xx from the refresh route is.
 *  * **A network failure is offline, not a sign-out**: it propagates as the
 *    transport error it is, cookies untouched.
 *
 * Memory, not a database: this process is the only one that holds the
 * browser's cookies, and the entries expire on their own. A second portal
 * replica would not share it — recorded here so scaling the portal reads
 * this first.
 */

export type TokenPair = { access_token: string; refresh_token?: string };

/** How long a completed exchange answers for its (now rotated) old token. */
const REMEMBER_MS = 60_000;

type Entry = { promise: Promise<TokenPair | null>; started: number };
const inFlight = new Map<string, Entry>();

/** Matches the login route; the cookie may expire slightly before the token. */
export const ACCESS_MAX_AGE = 15 * 60;

/**
 * Thirty days — owner decision D-26 (2026-09-20): a browser stays signed in
 * for as long as the person keeps using it, and is signed out one month
 * after its last use. "Same as Google login."
 *
 * This number and `LACTEVA_JWT_REFRESH_TTL_SECONDS` on the platform are the
 * SAME FACT written twice. The cookie and the token are stamped by the same
 * refresh (`storePair`, below, on every rotation), so they slide together and
 * expire together; when the month is up the browser discards the cookie and
 * the front door sends the person to a clean sign-in page. If the two drift,
 * the shorter one wins and the longer one is a lie — `auth-routes.test.ts`
 * reads the platform's setting from the tree and refuses the drift.
 */
export const REFRESH_MAX_AGE = 30 * 24 * 60 * 60;

/**
 * Exchange `refreshToken` for a new pair. Resolves to the pair, or to `null`
 * when the platform REFUSED (the session is over). Rejects on a transport
 * failure (offline), which the caller must not read as a refusal.
 */
export function refreshOnce(refreshToken: string): Promise<TokenPair | null> {
  const now = Date.now();
  const existing = inFlight.get(refreshToken);
  if (existing && now - existing.started < REMEMBER_MS) return existing.promise;

  const promise = (async () => {
    let upstream: Response;
    try {
      upstream = await fetch(`${backendUrl()}/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
    } catch (error) {
      // Offline: forget the attempt so the next request tries again, and
      // let the caller answer "the platform is unreachable".
      inFlight.delete(refreshToken);
      throw error;
    }
    if (!upstream.ok) return null;
    const pair = (await upstream.json()) as TokenPair;
    return pair.access_token ? pair : null;
  })();
  inFlight.set(refreshToken, { promise, started: now });
  // Housekeeping: drop expired memories so the map cannot grow with sessions.
  for (const [key, entry] of inFlight) {
    if (now - entry.started >= REMEMBER_MS) inFlight.delete(key);
  }
  return promise;
}

/** Put a fresh pair into the browser's cookies, exactly as login does. */
export async function storePair(pair: TokenPair): Promise<void> {
  const store = await cookies();
  store.set(ACCESS_COOKIE, pair.access_token, cookieOptions(ACCESS_MAX_AGE));
  if (pair.refresh_token) {
    store.set(REFRESH_COOKIE, pair.refresh_token, cookieOptions(REFRESH_MAX_AGE));
  }
}

/** The session is over: forget both cookies so nothing keeps sending them. */
export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

/** Tests only: forget every in-flight and remembered exchange. */
export function resetRefreshMemory(): void {
  inFlight.clear();
}
