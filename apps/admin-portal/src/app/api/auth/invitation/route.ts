import { NextResponse } from "next/server";
import { backendUrl, crossOriginRefused } from "@/lib/server/backend";

/**
 * Accept an invitation (LACTEVA-ADMIN-002).
 *
 * This exists for one reason: the call is PRE-AUTH. `/api/proxy` attaches the
 * session cookie and refuses a request that has none, which is correct for
 * every other path in the portal and exactly wrong here — the person accepting
 * an invitation has no account yet, and creating one is the point.
 *
 * So it is a dumb pipe, in the shape of `login/route.ts`: forward the body
 * WITHOUT a bearer token, return the platform's status and body verbatim.
 * Nothing is interpreted here. The platform owns whether a code is valid,
 * expired, already spent, or arriving too fast (it rate-limits this endpoint),
 * and each of those answers is a different sentence the person needs to read.
 *
 * The invitation token passes through this handler and is never logged, never
 * stored, and never returned — the response body is the platform's own, which
 * carries the new user and no token (SEC-003).
 */
export async function POST(request: Request) {
  if (crossOriginRefused(request)) {
    return NextResponse.json(
      { detail: "cross-origin request refused" },
      { status: 403 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "invalid request body" }, { status: 400 });
  }

  const upstream = await fetch(`${backendUrl()}/v1/invitations/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  // Verbatim, success or failure. "That code has already been used" and "that
  // code expired" are different problems with different remedies, and this
  // handler is not entitled to flatten them into one.
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
