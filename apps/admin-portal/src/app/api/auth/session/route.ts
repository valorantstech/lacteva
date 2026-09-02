import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  backendUrl,
  isTenantId,
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

  // WO-60: a PLATFORM session acting inside a tenant is asking about that
  // tenant. Without the header the platform answers `organization: null`,
  // which is why the chip could only show a truncated UUID and why an acting
  // administrator got no currency and no timezone either. A tenant-scoped
  // token ignores the header — the platform treats its own claim as
  // authoritative — so this is safe to send in both cases.
  const acting = await readActingTenant();
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl()}/v1/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(isTenantId(acting) ? { "X-Tenant-ID": acting } : {}),
      },
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
    { authenticated: true, ...me, acting_tenant_id: acting },
    { status: 200 },
  );
}
