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
  try {
    return new URL(origin).host !== new URL(request.url).host;
  } catch {
    return true; // an unparseable Origin is not one we trust
  }
}
