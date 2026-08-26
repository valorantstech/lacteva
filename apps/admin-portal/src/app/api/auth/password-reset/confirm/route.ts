import { NextResponse } from "next/server";
import { backendUrl, crossOriginRefused } from "@/lib/server/backend";

/**
 * Spend the reset code and set a new password (LACTEVA-ADMIN-003).
 *
 * PRE-AUTH and deliberately dumb, exactly like its sibling: the platform owns
 * whether a code is valid, expired, already spent or arriving too fast, and
 * each of those is a different sentence with a different remedy.
 *
 * The platform answers 204 — no body — so success here has nothing to carry,
 * and mints no session: resetting a password is not signing in.
 *
 * The code passes through and is never logged, stored or returned.
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

  const upstream = await fetch(`${backendUrl()}/v1/auth/password-reset/confirm`, {
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
