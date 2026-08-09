import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  backendUrl,
  cookieOptions,
  crossOriginRefused,
} from "@/lib/server/backend";

/** Matches `LACTEVA_JWT_ACCESS_TTL_SECONDS` / `..._REFRESH_TTL_SECONDS`. The
 *  cookie expiring slightly before the token is harmless; the reverse would
 *  send a dead token and read as a mysterious 401. */
const ACCESS_MAX_AGE = 15 * 60;
const REFRESH_MAX_AGE = 14 * 24 * 60 * 60;

/**
 * Exchange credentials for a session (PORTAL-001 / F-11).
 *
 * The browser posts here, not to the platform. The token comes back to this
 * server, goes into an HttpOnly cookie, and never reaches page script — which
 * is the whole difference from the `localStorage` it replaces.
 */
export async function POST(request: Request) {
  if (crossOriginRefused(request)) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "invalid request body" }, { status: 400 });
  }

  const upstream = await fetch(`${backendUrl()}/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!upstream.ok) {
    // Pass the platform's own problem document through unchanged. Inventing a
    // friendlier message here would hide a rate limit (429) behind "login
    // failed", and the operator needs to know which one it was.
    const detail = await upstream.text();
    return new NextResponse(detail, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
    });
  }

  const pair = (await upstream.json()) as {
    access_token: string;
    refresh_token?: string;
  };

  const store = await cookies();
  store.set(ACCESS_COOKIE, pair.access_token, cookieOptions(ACCESS_MAX_AGE));
  if (pair.refresh_token) {
    store.set(REFRESH_COOKIE, pair.refresh_token, cookieOptions(REFRESH_MAX_AGE));
  }
  // No body. Returning the token would undo the entire point.
  return new NextResponse(null, { status: 204 });
}
