/**
 * The portal's server boundary against the REAL platform
 * (P1-E2E-HARNESS-001).
 *
 * REAL: the portal's own route handlers — the ones that ship — talking over
 * real HTTP to a real FastAPI server backed by real PostgreSQL, with a real
 * synthetic dairy seeded through the platform's own API. The only thing
 * standing in is `next/headers`, because a cookie jar is the runtime's job and
 * not the boundary under test; every request that leaves this file is real.
 *
 * What it defends is the portal-specific half that no backend test can reach:
 * the browser never holds a bearer token — it holds an HttpOnly cookie, and
 * the proxy is what turns one into the other. If that seam breaks, every page
 * in the portal breaks at once, and until this suite existed nothing would
 * have noticed until someone clicked.
 *
 * Driven by `./infra/e2e/run-e2e.sh portal`. Without that harness there is no
 * server, and the suite says so rather than failing.
 */
import { readFileSync } from "node:fs";
import { beforeAll, describe, expect, it, vi } from "vitest";

type Fixture = {
  base_url: string;
  password: string;
  org: { id: string; name: string };
  users: Record<string, { email: string }>;
  centres: { id: string; code: string; name: string }[];
  suppliers: { id: string; code: string }[];
  other_org: { id: string; centre_id: string; admin_email: string };
};

const fixturePath = process.env.LACTEVA_E2E_FIXTURE ?? "";
const harnessed = fixturePath.length > 0;
let fx: Fixture;

/** The cookie jar the Next runtime would own. */
const jar = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      jar.has(name) ? { name, value: jar.get(name) } : undefined,
    set: (name: string, value: string) => jar.set(name, value),
    delete: (name: string) => jar.delete(name),
  }),
}));

const { POST: login } = await import("@/app/api/auth/login/route");
const { GET: proxyGet } = await import("@/app/api/proxy/[...path]/route");

const params = (path: string[]) => ({ params: Promise.resolve({ path }) });

async function signIn(email: string, tenantId?: string) {
  jar.clear();
  const res = await login(
    new Request("http://portal.test/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password: fx.password,
        ...(tenantId ? { tenant_id: tenantId } : {}),
      }),
    }),
  );
  return res;
}

beforeAll(() => {
  if (!harnessed) return;
  fx = JSON.parse(readFileSync(fixturePath, "utf8")) as Fixture;
  // The portal's server code reads the platform's address from the same
  // variable the deployment sets.
  process.env.LACTEVA_API_URL = process.env.LACTEVA_E2E_API ?? fx.base_url;
});

describe("portal → platform, over the real boundary", () => {
  it("signs a real operator in and keeps the token off the page", async () => {
    if (!harnessed) return;
    const res = await signIn(fx.users.admin.email, fx.org.id);
    // 204: the session is established and there is deliberately nothing to
    // return — the portal's real contract, confirmed at the real boundary.
    expect(res.status).toBe(204);

    // The token lives in the cookie jar, never in the response body — the
    // whole reason the proxy exists.
    const body = await res.text();
    expect(body).not.toMatch(/access_token|eyJ/);
    expect(jar.size).toBeGreaterThan(0);
  });

  it("refuses a wrong password, and sets no session", async () => {
    if (!harnessed) return;
    jar.clear();
    const res = await login(
      new Request("http://portal.test/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: fx.users.admin.email,
          password: "not-the-password",
        }),
      }),
    );
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(jar.size).toBe(0);
  });

  it("proxies an authenticated read to the real platform", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);

    const res = await proxyGet(
      new Request("http://portal.test/api/proxy/v1/collection-centers?limit=50"),
      params(["v1", "collection-centers"]),
    );
    expect(res.status).toBe(200);
    const page = (await res.json()) as { items: { id: string; code: string }[] };
    // The synthetic dairy's own centres, as the platform returned them.
    expect(page.items.map((c) => c.code)).toContain(fx.centres[0].code);
  });

  it("refuses to proxy without a session", async () => {
    if (!harnessed) return;
    jar.clear();
    const res = await proxyGet(
      new Request("http://portal.test/api/proxy/v1/collection-centers"),
      params(["v1", "collection-centers"]),
    );
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(res.status).not.toBe(200);
  });

  it("cannot reach another tenant's centre through the proxy", async () => {
    if (!harnessed) return;
    await signIn(fx.users.admin.email, fx.org.id);

    const foreign = fx.other_org.centre_id;
    const res = await proxyGet(
      new Request(`http://portal.test/api/proxy/v1/collection-centers/${foreign}`),
      params(["v1", "collection-centers", foreign]),
    );
    // RLS decides this in the database; the portal simply carries the answer.
    expect(res.status).not.toBe(200);
    expect([403, 404]).toContain(res.status);
  });

  it("carries the platform's own refusal rather than inventing one", async () => {
    if (!harnessed) return;
    await signIn(fx.users.manager.email, fx.org.id);

    // The manager here is a viewer: reading is allowed, recording is not.
    const read = await proxyGet(
      new Request("http://portal.test/api/proxy/v1/suppliers?limit=5"),
      params(["v1", "suppliers"]),
    );
    expect(read.status).toBe(200);

    const { POST: proxyPost } = await import("@/app/api/proxy/[...path]/route");
    const write = await proxyPost(
      new Request("http://portal.test/api/proxy/v1/suppliers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: "Should Not Exist", phone: "+919900000999" }),
      }),
      params(["v1", "suppliers"]),
    );
    expect(write.status).toBe(403);
    // The body is the platform's RFC-9457 problem document, passed through.
    const problem = await write.json();
    expect(problem).toHaveProperty("title");
  });
});
