/**
 * PORTAL-001 / F-09 + F-11 — the client's contract with the session.
 *
 * These are the assertions that would have caught the defect FINAL-001 found:
 * the portal used to read a bearer token out of `localStorage` and attach it
 * to every request, so any script on the page could read a live credential.
 * The token is now in an HttpOnly cookie the browser will not expose, and the
 * client goes through a same-origin proxy that attaches it server-side.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, login, logout, receiptDownloadUrl } from "@/lib/api";

function mockFetch(response: Partial<Response> & { json?: () => unknown }) {
  const spy = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => ({}),
    ...response,
  } as Response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request routing", () => {
  it("calls the portal's own proxy, never the platform directly", async () => {
    const fetchSpy = mockFetch({ json: async () => ({ total: 3 }) });
    await api("/v1/suppliers?limit=1");
    const [url] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/proxy/v1/suppliers?limit=1");
    expect(String(url)).not.toContain("http://");
  });

  it("never attaches an Authorization header — it has no credential to attach", async () => {
    const fetchSpy = mockFetch({ json: async () => ({}) });
    await api("/v1/collection-centers");
    const [, init] = fetchSpy.mock.calls[0];
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(Object.keys(headers).map((k) => k.toLowerCase())).not.toContain("authorization");
    expect((init as RequestInit).credentials).toBe("same-origin");
  });

  it("keeps the receipt download on the proxy so the PDF streams through", () => {
    expect(receiptDownloadUrl("r-1", "pdf")).toBe(
      "/api/proxy/v1/receipts/r-1/download?format=pdf",
    );
  });
});

describe("authentication", () => {
  it("posts credentials to the route handler and receives no token back", async () => {
    const fetchSpy = mockFetch({ status: 204, json: async () => ({}) });
    const result = await login("manager@kilima.example", "correct-horse-battery", "org-1");
    expect(result).toBeUndefined();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      email: "manager@kilima.example",
      password: "correct-horse-battery",
      tenant_id: "org-1",
    });
  });

  it("surfaces the platform's own problem detail when sign-in is refused", async () => {
    mockFetch({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({ title: "invalid_credentials", detail: "Email or password is incorrect." }),
    });
    await expect(login("a@b.example", "wrong-password")).rejects.toMatchObject({
      status: 401,
      detail: "Email or password is incorrect.",
    });
  });

  it("passes a rate limit through rather than calling it a login failure", async () => {
    mockFetch({
      ok: false,
      status: 429,
      statusText: "Too Many Requests",
      json: async () => ({ title: "rate_limited", detail: "Too many requests." }),
    });
    await expect(login("a@b.example", "whatever-password")).rejects.toMatchObject({ status: 429 });
  });

  it("signs out through the route handler, so the platform session dies too", async () => {
    const fetchSpy = mockFetch({ status: 204 });
    await logout();
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/auth/logout");
    expect((fetchSpy.mock.calls[0][1] as RequestInit).method).toBe("POST");
  });

  it("stores nothing in the browser — that is the whole point of F-11", async () => {
    mockFetch({ status: 204 });
    await login("a@b.example", "correct-horse-battery");
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });
});

describe("session probe (SESSION-001)", () => {
  it("asks a same-origin endpoint that answers 200 when nobody is signed in", async () => {
    const fetchSpy = mockFetch({ status: 200, json: async () => ({ authenticated: false }) });
    const { getSession } = await import("@/lib/api");
    await expect(getSession()).resolves.toEqual({ authenticated: false });
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/auth/session");
  });

  it("reports an unreachable portal distinctly from being signed out", async () => {
    mockFetch({ ok: false, status: 502, statusText: "Bad Gateway", json: async () => ({}) });
    const { getSession } = await import("@/lib/api");
    await expect(getSession()).resolves.toEqual({ authenticated: false, unreachable: true });
  });
});

describe("error handling", () => {
  it("raises ApiError carrying the problem detail and its structured extra", async () => {
    mockFetch({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({ title: "pricing_no_match", detail: "No applicable pricing.", extra: { stage: "band" } }),
    });
    let error: ApiError | undefined;
    try {
      await api("/v1/pricing");
    } catch (caught) {
      error = caught as ApiError;
    }
    expect(error).toBeInstanceOf(ApiError);
    expect(error?.status).toBe(409);
    expect(error?.detail).toBe("No applicable pricing.");
    expect(error?.extra).toEqual({ stage: "band" });
  });

  it("falls back to the status text when the body is not a problem document", async () => {
    mockFetch({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: async () => {
        throw new Error("not json");
      },
    });
    await expect(api("/v1/anything")).rejects.toMatchObject({ status: 502, detail: "Bad Gateway" });
  });

  it("returns undefined for 204 rather than trying to parse an empty body", async () => {
    mockFetch({ status: 204 });
    await expect(api("/v1/authz/assignments")).resolves.toBeUndefined();
  });
});

describe("unauthorized access", () => {
  /** Replaces jsdom's read-only location and records navigations. */
  function captureNavigation(pathname: string) {
    const navigations: string[] = [];
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        pathname,
        get href() {
          return pathname;
        },
        set href(value: string) {
          navigations.push(value);
        },
      },
    });
    return navigations;
  }

  it("does not redirect a session probe — a 401 is its answer (LOOP-001)", async () => {
    const navigations = captureNavigation("/login");
    mockFetch({ ok: false, status: 401, statusText: "Unauthorized", json: async () => ({}) });
    const { getMe } = await import("@/lib/api");
    await getMe().catch(() => undefined);
    expect(navigations).toEqual([]);
  });

  it("never navigates to /login from /login, whoever asks (LOOP-001)", async () => {
    const navigations = captureNavigation("/login");
    mockFetch({ ok: false, status: 401, statusText: "Unauthorized", json: async () => ({}) });
    await api("/v1/anything").catch(() => undefined);
    expect(navigations).toEqual([]);
  });

  it("sends the browser to the login page when the session is gone", async () => {
    const navigations = captureNavigation("/centers");
    mockFetch({ ok: false, status: 401, statusText: "Unauthorized", json: async () => ({}) });
    await api("/v1/suppliers").catch(() => undefined);
    expect(navigations).toEqual(["/login"]);
  });
});

describe("permission and tenant helpers (PERM-001 / TENANT-001)", () => {
  // DEMO-008 widened the session with the authorization context. The helpers
  // under test still care only about `permissions`; the rest is the shape the
  // backend now sends.
  const base = {
    authenticated: true as const,
    user: { id: "u1", email: "a@b.example", full_name: "A", locale: "en", is_active: true },
    acting_tenant_id: null,
    organization: null,
    membership: null,
    roles: [],
    center_scope: null,
  };

  it("answers false for a session that is not signed in", async () => {
    const { can } = await import("@/lib/api");
    expect(can(null, "audit.read")).toBe(false);
    expect(can({ authenticated: false }, "audit.read")).toBe(false);
  });

  it("grants only what the session lists", async () => {
    const { can } = await import("@/lib/api");
    const s = { ...base, tenant_id: "org-1", permissions: ["audit.read"] };
    expect(can(s, "audit.read")).toBe(true);
    expect(can(s, "identity.user.read")).toBe(false);
  });

  it("treats * as every permission — the platform wildcard", async () => {
    const { can } = await import("@/lib/api");
    const s = { ...base, tenant_id: null, permissions: ["*"] };
    expect(can(s, "anything.at.all")).toBe(true);
  });

  it("prefers the token's tenant over a selected one — the token is authoritative", async () => {
    const { actingTenant } = await import("@/lib/api");
    expect(actingTenant({ ...base, tenant_id: "from-token", acting_tenant_id: "chosen", permissions: [] })).toBe(
      "from-token",
    );
    expect(actingTenant({ ...base, tenant_id: null, acting_tenant_id: "chosen", permissions: [] })).toBe("chosen");
    expect(actingTenant({ ...base, tenant_id: null, permissions: [] })).toBeNull();
  });

  it("refuses to set an organization that is not a UUID", async () => {
    const { setActingTenant } = await import("@/lib/api");
    mockFetch({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({ detail: "tenant_id must be a UUID" }),
    });
    await expect(setActingTenant("not-a-uuid")).rejects.toMatchObject({ status: 400 });
  });
});
