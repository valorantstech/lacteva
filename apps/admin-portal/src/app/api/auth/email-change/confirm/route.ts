import { NextResponse } from "next/server";
import { backendUrl, crossOriginRefused } from "@/lib/server/backend";

/**
 * The NEW address confirms an email change (WO-87 §3).
 *
 * PRE-AUTH and deliberately dumb, exactly like the password-reset confirm:
 * the platform owns whether a code is valid, expired, cancelled, already
 * spent or arriving too fast, and each is a different sentence with a
 * different remedy. No bearer is forwarded — the person following the link
 * may hold no session, and the code alone is the credential.
 *
 * The platform answers 204 and revokes every session of that login, so
 * success here mints nothing and carries nothing. The code passes through and
 * is never logged, stored or returned.
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

  const upstream = await fetch(`${backendUrl()}/v1/auth/email-change/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (upstream.status === 204) return new NextResponse(null, { status: 204 });

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
