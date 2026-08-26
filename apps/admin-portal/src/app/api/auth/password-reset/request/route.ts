import { NextResponse } from "next/server";
import { backendUrl, crossOriginRefused } from "@/lib/server/backend";

/**
 * Ask for a reset code (LACTEVA-ADMIN-003).
 *
 * PRE-AUTH, for the same reason as the invitation route: `/api/proxy` attaches
 * the session cookie and refuses a request without one, and a locked-out
 * person has no session — that is the entire situation.
 *
 * A dumb pipe, and here that is a SECURITY property rather than a style. The
 * platform answers 202 whether or not the account exists, because any other
 * pair of answers turns this endpoint into a way to ask "is this person a
 * customer?". This handler must therefore not interpret, branch on, or
 * enrich the response: the moment it treats one outcome differently from the
 * other, the enumeration defence is gone no matter what the platform did.
 *
 * The email is forwarded and forgotten. Nothing is logged here.
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

  const upstream = await fetch(`${backendUrl()}/v1/auth/password-reset/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  // Verbatim — including a 429 from the rate limiter, which the person needs
  // to be told about honestly rather than have disguised as success.
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
