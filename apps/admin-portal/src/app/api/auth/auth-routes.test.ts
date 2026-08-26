/**
 * PORTAL-001 / F-11 — the server half of the session.
 *
 * The client tests prove the browser holds no credential. These prove the
 * server puts it somewhere the browser cannot read, refuses a cross-origin
 * attempt to spend it, and tears the platform session down on sign-out.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = {
  jar: new Map<string, { value: string; options: Record<string, unknown> }>(),
  get(name: string) {
    const entry = cookieStore.jar.get(name);
    return entry ? { name, value: entry.value } : undefined;
  },
  set(name: string, value: string, options: Record<string, unknown>) {
    cookieStore.jar.set(name, { value, options });
  },
  delete(name: string) {
    cookieStore.jar.delete(name);
  },
};

vi.mock("next/headers", () => ({ cookies: async () => cookieStore }));

process.env.LACTEVA_API_URL = "http://api.internal:8000";

const { POST: login } = await import("@/app/api/auth/login/route");
const { POST: logout } = await import("@/app/api/auth/logout/route");
const { POST: acceptInvitation } = await import(
  "@/app/api/auth/invitation/route"
);
const { ACCESS_COOKIE, REFRESH_COOKIE } = await import("@/lib/server/backend");

function request(url: string, init: RequestInit = {}) {
  return new Request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...init,
  });
}

beforeEach(() => {
  cookieStore.jar.clear();
  vi.unstubAllGlobals();
});

describe("login route", () => {
  it("puts the token in an HttpOnly, SameSite=Strict cookie and returns no body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ access_token: "at-123", refresh_token: "rt-456" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const response = await login(
      request("https://portal.example/api/auth/login", {
        body: JSON.stringify({ email: "a@b.example", password: "correct-horse-battery" }),
      }),
    );

    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");

    const access = cookieStore.jar.get(ACCESS_COOKIE)!;
    expect(access.value).toBe("at-123");
    expect(access.options.httpOnly).toBe(true);
    expect(access.options.sameSite).toBe("strict");
    expect(cookieStore.jar.get(REFRESH_COOKIE)!.value).toBe("rt-456");
  });

  it("passes the platform's refusal through with its own status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ title: "rate_limited" }), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const response = await login(
      request("https://portal.example/api/auth/login", {
        body: JSON.stringify({ email: "a@b.example", password: "x" }),
      }),
    );
    expect(response.status).toBe(429);
    expect(cookieStore.jar.size).toBe(0);
  });

  it("refuses a cross-origin sign-in attempt", async () => {
    const response = await login(
      request("https://portal.example/api/auth/login", {
        headers: { origin: "https://evil.example" },
        body: JSON.stringify({ email: "a@b.example", password: "x" }),
      }),
    );
    expect(response.status).toBe(403);
  });
});

describe("logout route", () => {
  it("revokes the platform session and clears both cookies", async () => {
    cookieStore.set(ACCESS_COOKIE, "at-123", {});
    cookieStore.set(REFRESH_COOKIE, "rt-456", {});
    const fetchSpy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchSpy);

    const response = await logout(request("https://portal.example/api/auth/logout"));

    expect(response.status).toBe(204);
    expect(fetchSpy.mock.calls[0][0]).toBe("http://api.internal:8000/v1/auth/logout");
    expect(cookieStore.jar.size).toBe(0);
  });

  it("still clears the cookies when the platform cannot be reached", async () => {
    cookieStore.set(ACCESS_COOKIE, "at-123", {});
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    const response = await logout(request("https://portal.example/api/auth/logout"));
    expect(response.status).toBe(204);
    expect(cookieStore.jar.size).toBe(0);
  });
});

/**
 * LACTEVA-ADMIN-002 — the pre-auth pipe.
 *
 * Accepting an invitation is the one write in the portal made by somebody who
 * has no session, because the request is what creates their account. It cannot
 * go through `/api/proxy`, which attaches the session cookie and refuses a
 * request without one. This route is therefore deliberately dumb, and these
 * tests hold it to that: no bearer, no interpretation, no cookie.
 */
describe("invitation accept route", () => {
  it("forwards to the platform with NO bearer token and sets no session", async () => {
    // A live session in the jar, to prove the route ignores it.
    cookieStore.set(ACCESS_COOKIE, "at-123", {});
    const fetchSpy = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: "u9", email: "new@dairy.example" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await acceptInvitation(
      request("https://portal.example/api/auth/invitation", {
        body: JSON.stringify({
          token: "code-abc",
          password: "correct-horse-battery",
          full_name: "Asha Verma",
        }),
      }),
    );

    expect(response.status).toBe(201);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.internal:8000/v1/invitations/accept");
    // The headers carry a content type and nothing else. A bearer here would
    // make the platform answer as the SIGNED-IN person, not the invitee.
    expect(
      (init.headers as Record<string, string>).Authorization,
    ).toBeUndefined();
    // No session was minted: joining is not signing in.
    expect(cookieStore.jar.get(REFRESH_COOKIE)).toBeUndefined();
    expect(cookieStore.jar.get(ACCESS_COOKIE)!.value).toBe("at-123");
  });

  it("returns the platform's refusal verbatim, status and body", async () => {
    const problem = {
      title: "invalid_token",
      status: 400,
      detail: "That invitation has expired.",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(problem), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const response = await acceptInvitation(
      request("https://portal.example/api/auth/invitation", {
        body: JSON.stringify({ token: "x", password: "y", full_name: "z" }),
      }),
    );

    // "Expired" and "already used" send a person to different places; the
    // pipe is not entitled to flatten them.
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual(problem);
  });

  it("refuses a cross-origin attempt", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const response = await acceptInvitation(
      request("https://portal.example/api/auth/invitation", {
        headers: { origin: "https://evil.example" },
        body: JSON.stringify({ token: "x", password: "y", full_name: "z" }),
      }),
    );
    expect(response.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
