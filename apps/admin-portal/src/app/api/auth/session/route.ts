import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  backendUrl,
  readAccessToken,
  readActingTenant,
} from "@/lib/server/backend";

/**
 * Who is signed in? (SESSION-001)
 *
 * Always 200. "Nobody" is a valid answer to this question, and encoding it as
 * a 401 made the browser log a red error on the login page — where being
 * signed out is the normal state — and made every caller treat a routine
 * answer as a failure to recover from. That is also what made the reload loop
 * possible (LOOP-001): a probe whose negative answer is an error invites a
 * redirect, and the redirect lands somewhere that probes again.
 *
 * A 401 from the platform still means something here — it means the cookie is
 * stale — so it is cleared on the way out rather than left to fail the next
 * request too.
 */
export async function GET() {
  const token = await readAccessToken();
  if (!token) {
    return NextResponse.json({ authenticated: false }, { status: 200 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl()}/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    // The platform is unreachable. Distinct from "signed out": the caller
    // should say so rather than quietly offering a sign-in link.
    return NextResponse.json(
      { authenticated: false, unreachable: true },
      { status: 200 },
    );
  }

  if (upstream.status === 401) {
    const store = await cookies();
    store.delete(ACCESS_COOKIE);
    store.delete(REFRESH_COOKIE);
    return NextResponse.json({ authenticated: false }, { status: 200 });
  }

  if (!upstream.ok) {
    return NextResponse.json({ authenticated: false }, { status: 200 });
  }

  const me = (await upstream.json()) as Record<string, unknown>;
  // TENANT-001: `tenant_id` is what the TOKEN carries (null for a platform
  // session); `acting_tenant_id` is the organization this browser selected.
  // The nav needs both to say "you are platform-level, currently acting in X".
  return NextResponse.json(
    { authenticated: true, ...me, acting_tenant_id: await readActingTenant() },
    { status: 200 },
  );
}
