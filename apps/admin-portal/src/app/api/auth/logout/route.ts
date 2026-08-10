import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  TENANT_COOKIE,
  backendUrl,
  crossOriginRefused,
  readAccessToken,
} from "@/lib/server/backend";

/**
 * End the session on both sides (PORTAL-001 / F-11).
 *
 * Clearing the cookie alone would leave the platform-side `auth_session` live
 * until it expired, so a captured refresh token would still work — the same
 * gap SEC-003/F-02 closed for deactivation. The platform call is best-effort:
 * if it fails the cookies still go, because a logout that leaves the browser
 * holding a session because the network blipped is worse than a session row
 * that outlives its browser.
 */
export async function POST(request: Request) {
  if (crossOriginRefused(request)) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }

  const token = await readAccessToken();
  if (token) {
    try {
      await fetch(`${backendUrl()}/v1/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // best effort — see above
    }
  }

  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
  // TENANT-001: the next person at this browser must not inherit the last
  // administrator's choice of organization.
  store.delete(TENANT_COOKIE);
  return new NextResponse(null, { status: 204 });
}
