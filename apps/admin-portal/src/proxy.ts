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

// WO-79: the SAME declarations the server routes use, from a module with no
// imports so the edge runtime can take it. This file used to redeclare the
// access cookie's name "kept in step" with `lib/server/backend.ts`, and did
// not know the refresh cookie existed — which is how WO-73 could give the
// portal a fortnight of session the front door did not recognise.
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/session-cookies";

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
  // WO-87: the page the NEW address opens to confirm an email change. The
  // person may hold no session; the code is the credential.
  "/confirm-email",
  // WO-86: the page a household's bill link opens. The link IS the credential
  // — a token in the path, checked by the platform — and the reader has no
  // account by design.
  "/bill",
  // The portal's own session/proxy handlers. They are the thing that SETS the
  // cookie, so requiring one here would be a loop.
  "/api",
] as const;

export function isPublic(pathname: string): boolean {
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

/**
 * The sign-in page's path for somebody who was going to `target` — the ONE
 * spelling of it, used by the guard below and by the shell when a session it
 * held turns out to have ended (WO-79 part 5), so the two cannot disagree
 * about what `next=` looks like. `/` carries no `next=`: there is nothing to
 * come back to.
 */
export function loginPath(target: string): string {
  const next = safeNext(target);
  if (!next || next === "/") return "/login";
  return `/login?${new URLSearchParams({ next })}`;
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (isPublic(pathname)) return NextResponse.next();
  // A session is present when EITHER cookie is (WO-79). The access cookie
  // lives fifteen minutes; the refresh cookie lives thirty days from its last
  // use (D-26). Close the tab, come back after lunch: the browser has
  // discarded `lacteva_session` and still holds `lacteva_refresh`, and that
  // person is signed in — the session probe every page runs first renews the
  // dead access cookie from the refresh cookie (WO-73). Checking only the
  // access cookie here sent every returning user to /login, where the shell
  // then probed, renewed, and drew the signed-in chrome around the sign-in
  // form: the screenshot of 2026-09-20.
  if (request.cookies.get(ACCESS_COOKIE) || request.cookies.get(REFRESH_COOKIE)) {
    return NextResponse.next();
  }

  // Neither cookie, on a route that needs a session: the sign-in page,
  // carrying where they were going. A cookie's mere PRESENCE is what is
  // checked here — whether it is still valid is the platform's answer. A
  // refresh the platform refuses (the month is up, the session was revoked,
  // a rotated token was reused) is what clears both cookies and shows the
  // signed-out state; the shell then brings that person here (part 5).
  // Deciding validity here would mean a round trip to the API on every
  // navigation.
  return NextResponse.redirect(new URL(loginPath(`${pathname}${search}`), request.url));
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
