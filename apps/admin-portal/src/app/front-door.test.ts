/**
 * The front door (WO-59 · LACTEVA-ADMIN-019).
 *
 * An anonymous visitor to the live portal got the dashboard's signed-out
 * empty state instead of a sign-in page. Not a data leak — the API refuses
 * every unauthenticated call and the shell had nothing but dashes in it —
 * but a product that asks somebody who cannot use it to find the login
 * themselves.
 *
 * These pin the four things that can go wrong with a guard like this:
 * it must catch the authenticated routes, it must NOT catch the public ones
 * (an invitation link bouncing a new user to a login they cannot pass would
 * be worse than the defect), it must bring people back to what they asked
 * for, and it must refuse to bring them anywhere else.
 */
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { loginPath, proxy, safeNext } from "@/proxy";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/server/backend";

const SESSION = "lacteva_session";
const REFRESH = "lacteva_refresh";

function visit(path: string, { signedIn = false, refreshOnly = false } = {}) {
  const request = new NextRequest(new URL(`https://portal.example${path}`));
  if (signedIn) request.cookies.set(SESSION, "a-token");
  if (refreshOnly) request.cookies.set(REFRESH, "a-refresh-token");
  return proxy(request);
}

const location = (response: Response) => response.headers.get("location");

describe("an anonymous visitor is shown the door they can open", () => {
  it("redirects the root to the sign-in page", () => {
    const response = visit("/");
    expect(response.status).toBe(307);
    expect(location(response)).toBe("https://portal.example/login");
  });

  it("redirects a deep authenticated route and remembers where they were going", () => {
    const response = visit("/settlements?status=finalized");
    expect(location(response)).toBe(
      "https://portal.example/login?next=%2Fsettlements%3Fstatus%3Dfinalized",
    );
  });

  it("does not put ?next=/ on the root — there is nothing to come back to", () => {
    expect(location(visit("/"))).not.toContain("next=");
  });
});

describe("the public routes stay public", () => {
  // The one this guard could most easily break: a colleague following an
  // invitation has no account yet, and a login they cannot pass is a dead end.
  it.each([
    "/login",
    "/login?notice=reset",
    "/reset-password",
    "/reset-password?token=abc",
    "/accept-invitation",
    "/accept-invitation?token=abc",
    "/confirm-email",
    "/confirm-email?token=abc",
    "/api/auth/session",
  ])("%s is served, not redirected", (path) => {
    const response = visit(path);
    expect(response.status).toBe(200);
    expect(location(response)).toBeNull();
  });
});

describe("a signed-in visitor is left alone", () => {
  it.each(["/", "/settlements", "/transactions/abc"])(
    "%s renders as it always did",
    (path) => {
      const response = visit(path, { signedIn: true });
      expect(response.status).toBe(200);
      expect(location(response)).toBeNull();
    },
  );
});

describe("a visitor whose access cookie has expired is still signed in (WO-79)", () => {
  // The access cookie lives fifteen minutes; the refresh cookie a month from
  // its last use. Back from lunch, the browser holds only the second — and
  // that person is signed in: the session probe renews the first from it.
  // Checking the access cookie alone sent every returning user to /login,
  // where the shell then renewed the session and drew the signed-in chrome
  // around the sign-in form.
  it.each(["/", "/settlements", "/transactions/abc"])(
    "%s is served to a visitor holding ONLY lacteva_refresh",
    (path) => {
      const response = visit(path, { refreshOnly: true });
      expect(response.status).toBe(200);
      expect(location(response)).toBeNull();
    },
  );

  it("the names the front door checks are the names the server sets", () => {
    // The proxy cannot import the server-only module, so both take the
    // names from `lib/session-cookies.ts` — and the proxy carries no literal
    // of its own that could drift from them.
    expect([SESSION, REFRESH]).toEqual([ACCESS_COOKIE, REFRESH_COOKIE]);
    const source = readFileSync(resolve(__dirname, "../proxy.ts"), "utf8");
    expect(source).toContain('from "@/lib/session-cookies"');
    expect(source).not.toContain('"lacteva_session"');
    expect(source).not.toContain('"lacteva_refresh"');
  });

  it("with neither cookie the redirect stands", () => {
    // Not a repeat of the anonymous tests above: this pins that the OR did
    // not become "let everybody through".
    expect(visit("/settlements").status).toBe(307);
  });
});

describe("the sign-in path is spelled once (WO-79 part 5)", () => {
  // The shell sends a dead session to the same address the guard would
  // have, so they cannot disagree about what next= looks like.
  it("carries the destination, and nothing for the root", () => {
    expect(loginPath("/settlements?status=finalized")).toBe(
      "/login?next=%2Fsettlements%3Fstatus%3Dfinalized",
    );
    expect(loginPath("/")).toBe("/login");
    expect(loginPath("//evil.example")).toBe("/login");
  });

  it("is what the guard redirects to", () => {
    const redirect = location(visit("/payments?status=failed"))!;
    expect(new URL(redirect).pathname + new URL(redirect).search).toBe(
      loginPath("/payments?status=failed"),
    );
  });
});

describe("the round trip lands where the visitor was going", () => {
  it("the guard's next= is exactly what the login page will navigate to", () => {
    // Both halves run the same `safeNext`, so what the guard emits is what
    // the form consumes — a check on the way out that is not repeated on the
    // way in is not a check.
    const redirect = location(visit("/payments?status=failed"));
    const next = new URL(redirect!).searchParams.get("next");
    expect(safeNext(next)).toBe("/payments?status=failed");
  });
});

describe("next= accepts a path on this site and nothing else", () => {
  it("keeps a plain path, with its query and hash", () => {
    expect(safeNext("/settlements?status=finalized#total")).toBe(
      "/settlements?status=finalized#total",
    );
  });

  // The open-redirect refusals. Each of these, accepted, would turn the
  // portal's own sign-in page into a link that lands somebody on a site
  // somebody else controls — with the credibility of this domain behind it.
  it.each([
    ["an absolute URL", "https://evil.example/steal"],
    ["a protocol-relative URL", "//evil.example/steal"],
    ["a backslash-escaped host", "/\\evil.example/steal"],
    ["another scheme", "javascript:alert(1)"],
    ["a bare host", "evil.example"],
    ["nothing at all", ""],
  ])("refuses %s", (_why, target) => {
    expect(safeNext(target)).toBeNull();
  });

  it("never emits a next= the browser would follow off-site", () => {
    const response = proxy(
      new NextRequest(new URL("https://portal.example//evil.example")),
    );
    expect(location(response)).toBe("https://portal.example/login");
  });
});
