/**
 * PORTAL-001 / F-11 — the proxy is where the credential is added.
 *
 * If this attaches the token when it should not, or fails to when it should,
 * every page is wrong at once. It is also the only place a cross-origin
 * request could spend a session, so the Origin check is asserted here rather
 * than assumed from `SameSite`.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = {
  jar: new Map<string, string>(),
  get(name: string) {
    const value = cookieStore.jar.get(name);
    return value ? { name, value } : undefined;
  },
  set() {},
  delete(name: string) {
    cookieStore.jar.delete(name);
  },
};

vi.mock("next/headers", () => ({ cookies: async () => cookieStore }));

process.env.LACTEVA_API_URL = "http://api.internal:8000";

const { GET, POST, DELETE } = await import("@/app/api/proxy/[...path]/route");
const { ACCESS_COOKIE } = await import("@/lib/server/backend");

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });

beforeEach(() => {
  cookieStore.jar.clear();
  vi.unstubAllGlobals();
});

describe("proxy", () => {
  it("attaches the cookie's token as a bearer header the browser never sees", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, "at-123");
    const fetchSpy = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ total: 2 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const response = await GET(
      new Request("https://portal.example/api/proxy/v1/suppliers?limit=1"),
      context(["v1", "suppliers"]),
    );

    expect(response.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("http://api.internal:8000/v1/suppliers?limit=1");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer at-123");
  });

  it("answers 401 in the platform's own shape when there is no session", async () => {
    const response = await GET(
      new Request("https://portal.example/api/proxy/v1/suppliers"),
      context(["v1", "suppliers"]),
    );
    expect(response.status).toBe(401);
    expect(await response.json()).toMatchObject({ title: "unauthorized" });
  });

  it("refuses a cross-origin state-changing request", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, "at-123");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await POST(
      new Request("https://portal.example/api/proxy/v1/payments", {
        method: "POST",
        headers: { origin: "https://evil.example" },
        body: "{}",
      }),
      context(["v1", "payments"]),
    );

    expect(response.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards DELETE with its query string, which is how role revocation works", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, "at-123");
    const fetchSpy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchSpy);

    const response = await DELETE(
      new Request("https://portal.example/api/proxy/v1/authz/assignments?user_id=u1&role_name=tenant-admin", {
        method: "DELETE",
      }),
      context(["v1", "authz", "assignments"]),
    );

    expect(response.status).toBe(204);
    expect(fetchSpy.mock.calls[0][0]).toBe(
      "http://api.internal:8000/v1/authz/assignments?user_id=u1&role_name=tenant-admin",
    );
    expect(fetchSpy.mock.calls[0][1].method).toBe("DELETE");
  });

  it("reports an unreachable platform as 502, not as its own failure", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, "at-123");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));
    const response = await GET(
      new Request("https://portal.example/api/proxy/v1/suppliers"),
      context(["v1", "suppliers"]),
    );
    expect(response.status).toBe(502);
  });

  it("preserves the upstream content type so a receipt still downloads as a PDF", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, "at-123");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("%PDF-1.4", {
          status: 200,
          headers: {
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="RCP-2026-000001.pdf"',
          },
        }),
      ),
    );
    const response = await GET(
      new Request("https://portal.example/api/proxy/v1/receipts/r1/download?format=pdf"),
      context(["v1", "receipts", "r1", "download"]),
    );
    expect(response.headers.get("Content-Type")).toBe("application/pdf");
    expect(response.headers.get("Content-Disposition")).toContain("RCP-2026-000001.pdf");
  });
});
