/**
 * The front door sends you to the front door (WO-59 · LACTEVA-ADMIN-019).
 *
 * An anonymous visitor to dev.phoenixsoft.in got the DASHBOARD — signed-out,
 * empty, every tile a dash — instead of the sign-in page. Every deep route
 * answered 200 to a stranger and rendered its own empty state, because
 * nothing in the portal ever redirected to `/login`.
 *
 * **This is a routing and UX defect, not a security one, and it is worth
 * saying plainly.** The platform refuses every unauthenticated call, the
 * session cookie is HTTP-only, and no page ever held data to leak: what the
 * visitor saw was a shell full of dashes. What was wrong is that the product
 * asked somebody who cannot use it to work out for themselves where to sign
 * in. The guard below is the front door, not a wall — the walls are the API's.
 *
 * ONE MECHANISM, NOT N REDIRECTS. A per-page check would be the same decision
 * copied into thirty files, and the thirty-first page would be written without
 * it. This runs before any of them, on the routes that need a session, and
 * every public route is named here rather than remembered.
 *
 * NEXT 16: this file is `proxy.ts`, not `middleware.ts` — the convention was
 * renamed in this major version and the old name is deprecated. Same
 * semantics, different filename and export.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** The cookie `POST /api/auth/login` sets. Kept in step with `lib/server/backend.ts`. */
const ACCESS_COOKIE = "lacteva_session";

/**
 * Routes a person must be able to reach WITHOUT a session.
 *
 * An invitation link is the load-bearing one: a new colleague following it has
 * no account yet, and bouncing them to a login they cannot pass would make the
 * invitation useless — the failure this guard would be most likely to cause,
 * so it is the one most carefully excluded. Password reset is the same shape.
 */
const PUBLIC_PREFIXES = [
  "/login",
  "/reset-password",
  "/accept-invitation",
  // The portal's own session/proxy handlers. They are the thing that SETS the
  // cookie, so requiring one here would be a loop.
  "/api",
] as const;

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Where to send a visitor back to after they sign in — or nothing.
 *
 * ONLY a same-origin, path-absolute URL is accepted. `//evil.example` is a
 * protocol-relative URL that browsers follow off-site, and it survives a naive
 * `startsWith("/")` check; an absolute `https://evil.example` obviously does;
 * a backslash is normalised to a slash by some browsers, so `/\evil.example`
 * is the same trick wearing a different hat. Anything that is not a plain
 * `/path` is dropped and the visitor simply lands on the dashboard, which is
 * the correct amount of harm for a link somebody tampered with.
 */
export function safeNext(target: string | null | undefined): string | null {
  if (!target) return null;
  if (!target.startsWith("/")) return null;
  if (target.startsWith("//") || target.startsWith("/\\")) return null;
  // A parseable absolute URL means the string named a host; `new URL` with a
  // base only succeeds on a relative path when that path is genuinely relative.
  try {
    const url = new URL(target, "http://portal.invalid");
    if (url.origin !== "http://portal.invalid") return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (isPublic(pathname)) return NextResponse.next();
  if (request.cookies.get(ACCESS_COOKIE)) return NextResponse.next();

  // Signed out, on a route that needs a session: the sign-in page, carrying
  // where they were going. The cookie's mere presence is what is checked here
  // — whether it is still VALID is the platform's answer, and a stale cookie
  // lands on the dashboard, which clears it and shows the signed-out state.
  // Deciding that here would mean a round trip to the API on every navigation.
  const login = new URL("/login", request.url);
  const next = safeNext(`${pathname}${search}`);
  if (next && next !== "/") login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  /**
   * Everything except the framework's own assets and the public files nginx
   * serves. Without a matcher this would also run on `_next/static`, which
   * would put a redirect in front of the stylesheet of the very page it
   * redirects to.
   */
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon.png|apple-icon.png|manifest.webmanifest|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml|json)$).*)",
  ],
};
