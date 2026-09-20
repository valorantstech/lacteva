import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  TENANT_COOKIE,
  crossOriginRefused,
  isTenantId,
  readAccessToken,
} from "@/lib/server/backend";
import { REFRESH_MAX_AGE } from "@/lib/server/refresh";

/**
 * Choose which organization a platform-level session acts inside (TENANT-001).
 *
 * There is deliberately no "list every tenant" call behind this: the platform
 * does not expose one, and a portal that invented a way to enumerate every
 * organization would be building a capability the API has chosen not to give.
 * The administrator names the organization they mean.
 */
export async function POST(request: Request) {
  if (crossOriginRefused(request)) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }
  // Requires a session: without one there is nothing to scope, and an
  // unauthenticated caller must not be able to leave state on the browser.
  if (!(await readAccessToken())) {
    return NextResponse.json({ detail: "not signed in" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "invalid request body" }, { status: 400 });
  }
  const tenantId = (body as { tenant_id?: unknown })?.tenant_id;
  if (!isTenantId(tenantId)) {
    return NextResponse.json(
      { detail: "tenant_id must be a UUID — copy it from the organization page" },
      { status: 400 },
    );
  }

  const store = await cookies();
  // WO-79 / D-26: as long as the session itself, from the same constant. A
  // platform administrator whose session outlived their organisation choice
  // (this was a fourteen-day literal beside a thirty-day session) would find
  // themselves signed in and acting in nothing, with every page a 403.
  store.set(TENANT_COOKIE, tenantId, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  });
  return new NextResponse(null, { status: 204 });
}

/** Stop acting inside a tenant. */
export async function DELETE(request: Request) {
  if (crossOriginRefused(request)) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }
  const store = await cookies();
  store.delete(TENANT_COOKIE);
  return new NextResponse(null, { status: 204 });
}
