import "server-only";

import { cookies } from "next/headers";

/**
 * Where the platform API lives, from the SERVER's point of view.
 *
 * PORTAL-001 / F-03. This is deliberately not `NEXT_PUBLIC_API_URL`. Next
 * inlines `NEXT_PUBLIC_*` into the client bundle at BUILD time, which meant
 * one image could only ever talk to one backend, and an image built without
 * the variable shipped `http://localhost:8000` to production browsers. Read
 * here, on the server, at REQUEST time: the same image runs in staging and
 * production, and the browser never learns the backend's address at all.
 */
export function backendUrl(): string {
  const url = process.env.LACTEVA_API_URL;
  if (!url) {
    throw new Error(
      "LACTEVA_API_URL is not set — the portal has no platform API to talk to. " +
        "Set it in the portal service's environment (see DEPLOYMENT.md §Portal).",
    );
  }
  return url.replace(/\/$/, "");
}

/** PORTAL-001 / F-11: the session cookies. Names are stable — nginx, the
 *  proxy and the tests all agree on them. */
export const ACCESS_COOKIE = "lacteva_session";
export const REFRESH_COOKIE = "lacteva_refresh";

/**
 * TENANT-001: which organization a PLATFORM-level session is acting inside.
 *
 * A platform administrator's token carries no tenant, and every business
 * endpoint calls `require_current_tenant()` — so without this the account with
 * `*` permissions got 403 from almost every page in the portal. The platform
 * has always supported `X-Tenant-ID` for exactly this ("platform-level
 * principals may act inside a tenant, permission-guarded per route"); the
 * portal simply never sent it.
 *
 * A cookie, not a URL parameter or client state: the proxy is the only thing
 * that talks to the platform, so the choice has to survive on the server side
 * of that boundary. Not HttpOnly-critical — an organization id is not a
 * secret — but kept `HttpOnly` anyway so page script cannot quietly retarget
 * a request the user did not choose.
 */
export const TENANT_COOKIE = "lacteva_tenant";

/**
 * Cookie attributes for a credential the browser must never read.
 *
 * `httpOnly` is the point of the exercise: script cannot reach it, so an XSS
 * that would previously have exfiltrated the token from `localStorage` now
 * gets nothing. `sameSite: "strict"` is the CSRF defence — the cookie is not
 * attached to any request the browser did not initiate from this origin,
 * which is what makes a cookie-backed session safe without a token dance.
 * `secure` follows the deployment: always on behind TLS, off only for plain
 * HTTP development, because a `Secure` cookie is silently dropped there and
 * the symptom is an unexplained login loop.
 */
export function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

export async function readAccessToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(ACCESS_COOKIE)?.value ?? null;
}

export async function readRefreshToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value ?? null;
}

export async function readActingTenant(): Promise<string | null> {
  const store = await cookies();
  return store.get(TENANT_COOKIE)?.value ?? null;
}

/** A tenant id is a UUID or it is nothing — never forward what a caller made
 *  up, so the platform is asked a well-formed question or none at all. */
export function isTenantId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
  );
}

/**
 * Reject a state-changing request that did not come from this origin.
 *
 * Defence in depth behind `SameSite=Strict`, which already stops the browser
 * attaching the session cookie cross-site. Belt and braces here because the
 * cost is one string comparison and the failure mode is somebody else's
 * page spending our session.
 */
export function crossOriginRefused(request: Request): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return false;
  const origin = request.headers.get("origin");
  if (!origin) return false; // same-origin fetches may omit it

  // AWS-001: compare against the host the BROWSER addressed, not the one this
  // process was reached on.
  //
  // `new URL(request.url).host` is the upstream address behind a reverse
  // proxy — `portal:3000` on the compose network — so every state-changing
  // request from a real browser (`Origin: https://the-public-host`) was
  // refused with 403 and the portal was unusable the moment it sat behind
  // nginx. Found by logging in to the deployed stack.
  //
  // `Host`/`X-Forwarded-Host` is the right thing to compare with: a browser
  // sets both `Origin` and `Host` itself and a cross-site page cannot forge
  // either, which is exactly what makes Origin-vs-Host a CSRF check.
  const expected =
    request.headers.get("x-forwarded-host") ??
    request.headers.get("host") ??
    (() => {
      try {
        return new URL(request.url).host;
      } catch {
        return null;
      }
    })();
  if (!expected) return true;
  try {
    return new URL(origin).host !== expected;
  } catch {
    return true; // an unparseable Origin is not one we trust
  }
}
