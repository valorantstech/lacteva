import { NextResponse } from "next/server";
import { backendUrl } from "@/lib/server/backend";

/**
 * A household's bills, by link (WO-86).
 *
 * PRE-AUTH, in the shape of `auth/invitation/route.ts`: the reader has no
 * session and the point of the page is that they never need one. `/api/proxy`
 * attaches the session cookie and refuses a request without one, which is
 * right everywhere else and wrong here — so this is a dumb pipe that forwards
 * the token in the path and NOTHING from the browser's cookies.
 *
 * Two headers do travel. The visitor's address, so the platform's per-IP rate
 * limit sees the visitor rather than this server (the deployment contract
 * lets only the load balancer set `X-Forwarded-For`; this handler passes on
 * what that balancer set). And `Accept-Language`, for the platform's
 * negotiation on a request that never authenticates.
 *
 * The platform's answer comes back verbatim, status and body, and so do the
 * two headers that keep the page out of indexes and caches. Nothing here
 * interprets the token or logs it; it is in the URL the visitor already has.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ token: string }> },
) {
  const { token } = await context.params;
  if (!token || token.length > 128) {
    return NextResponse.json({ detail: "not found" }, { status: 404 });
  }
  const headers: Record<string, string> = {};
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) headers["X-Forwarded-For"] = forwarded;
  const language = request.headers.get("accept-language");
  if (language) headers["Accept-Language"] = language;

  const upstream = await fetch(
    `${backendUrl()}/v1/public/bill/${encodeURIComponent(token)}`,
    { headers, cache: "no-store" },
  );
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "application/json",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex, nofollow",
    },
  });
}
