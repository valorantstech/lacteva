import { NextResponse } from "next/server";
import {
  backendUrl,
  crossOriginRefused,
  readAccessToken,
  readActingTenant,
  readRefreshToken,
} from "@/lib/server/backend";
import { clearSession, refreshOnce, storePair } from "@/lib/server/refresh";

/**
 * The portal's only route to the platform (PORTAL-001 / F-11).
 *
 * Every page calls same-origin `/api/proxy/...`; this attaches the bearer
 * token from the HttpOnly cookie and forwards. Three things follow, and all
 * three were the point:
 *
 *  * page script never holds a credential, so an XSS has nothing to steal;
 *  * the browser never learns the platform's address, so the API needs no
 *    public hostname and no CORS entry for the portal;
 *  * the backend stays bearer-only and CSRF-free exactly as divergence #22
 *    describes — the cookie lives between the browser and THIS server, and
 *    goes no further.
 *
 * Deliberately a dumb pipe. It does not interpret, cache or reshape anything:
 * the moment it starts having opinions about the API it becomes a second
 * place where the contract lives.
 */
async function forward(request: Request, path: string[]) {
  if (crossOriginRefused(request)) {
    return NextResponse.json({ detail: "cross-origin request refused" }, { status: 403 });
  }

  let token = await readAccessToken();
  const refreshToken = await readRefreshToken();
  if (!token && !refreshToken) {
    // The shape the platform itself uses, so the client's error handling does
    // not need a special case for "not signed in".
    return NextResponse.json(
      { title: "unauthorized", detail: "Authentication is required.", status: 401 },
      { status: 401 },
    );
  }

  const search = new URL(request.url).search;
  const target = `${backendUrl()}/${path.map(encodeURIComponent).join("/")}${search}`;

  // TENANT-001: a platform-level session acts inside the organization it
  // selected. A tenant-scoped token carries its own tenant and the platform
  // treats the token as authoritative, so sending this alongside one changes
  // nothing — which is why it is safe to send whenever it is set.
  const actingTenant = await readActingTenant();
  const headersFor = (bearer: string) => {
    const headers = new Headers();
    headers.set("Authorization", `Bearer ${bearer}`);
    if (actingTenant) headers.set("X-Tenant-ID", actingTenant);
    for (const name of ["content-type", "accept", "accept-language", "idempotency-key"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    return headers;
  };

  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
  const unreachable = () =>
    // The platform is unreachable. 502 rather than 500: this server is fine,
    // the one behind it is not, and an operator reading nginx logs needs to
    // be able to tell those apart.
    NextResponse.json(
      { title: "bad_gateway", detail: "The platform API is unreachable.", status: 502 },
      { status: 502 },
    );
  const send = (bearer: string) =>
    fetch(target, {
      method: request.method,
      headers: headersFor(bearer),
      body,
      cache: "no-store",
      redirect: "manual",
    });

  // WO-73: an expired ACCESS token is not an expired session. The access
  // cookie lives fifteen minutes and the browser stops sending it when it
  // dies, so "no access cookie but a refresh cookie" and "the platform said
  // 401 to the access token" are the same situation: refresh once (shared
  // with every other request that met it at the same moment), store the new
  // pair, and replay this request. Only a REFUSED refresh ends the session.
  const renew = async (): Promise<Response | null> => {
    if (!refreshToken) return null;
    let pair;
    try {
      pair = await refreshOnce(refreshToken);
    } catch {
      return unreachable();
    }
    if (!pair) {
      await clearSession();
      return NextResponse.json(
        { title: "unauthorized", detail: "Your session has ended. Sign in again.", status: 401 },
        { status: 401 },
      );
    }
    await storePair(pair);
    token = pair.access_token;
    return null;
  };

  if (!token) {
    const ended = await renew();
    if (ended) return ended;
  }

  let upstream: Response;
  try {
    upstream = await send(token!);
  } catch {
    return unreachable();
  }
  if (upstream.status === 401 && refreshToken) {
    const ended = await renew();
    if (ended) return ended;
    try {
      upstream = await send(token!);
    } catch {
      return unreachable();
    }
    if (upstream.status === 401) {
      // The platform refused the token it just issued: nothing more to try.
      await clearSession();
    }
  }

  // Stream the body through untouched — receipts come back as application/pdf.
  const responseHeaders = new Headers();
  for (const name of ["content-type", "content-disposition", "content-length"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
export async function POST(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
export async function PUT(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
export async function PATCH(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
export async function DELETE(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
