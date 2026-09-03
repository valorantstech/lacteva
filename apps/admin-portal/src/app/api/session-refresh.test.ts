/**
 * WO-73 — the portal must not eject the person using it.
 *
 * The portal-side twin of WO-69: a 900-second access token, a fourteen-day
 * refresh token the login route stored and nothing ever spent. On a 401 the
 * proxy ended the session — every quarter of an hour, for anyone actually
 * working — and it ended its own discoverer's session mid-verification.
 *
 * Pinned here, each because it is a way this goes wrong:
 *   1. six concurrent 401s → ONE refresh (the platform rotates refresh
 *      tokens and treats reuse as theft, so six would kill the session);
 *   2. the original request is replayed and the caller sees a 200;
 *   3. a REFUSED refresh ends the session — both cookies cleared, 401;
 *   4. a network failure during the refresh is offline (502), not a sign-out;
 *   5. an access cookie the browser has already dropped (its max-age is the
 *      token's) still leads to a refresh, not to "not signed in";
 *   6. the session probe renews too, so the first thing a stale tab does
 *      does not answer "nobody".
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

type Jar = Map<string, { value: string; options?: unknown }>;
const cookieStore = {
  jar: new Map() as Jar,
  get(name: string) {
    const entry = cookieStore.jar.get(name);
    return entry ? { name, value: entry.value } : undefined;
  },
  set(name: string, value: string, options?: unknown) {
    cookieStore.jar.set(name, { value, options });
  },
  delete(name: string) {
    cookieStore.jar.delete(name);
  },
};

vi.mock("next/headers", () => ({ cookies: async () => cookieStore }));

process.env.LACTEVA_API_URL = "http://api.internal:8000";

const { GET: proxyGET } = await import("@/app/api/proxy/[...path]/route");
const { GET: sessionGET } = await import("@/app/api/auth/session/route");
const { ACCESS_COOKIE, REFRESH_COOKIE } = await import("@/lib/server/backend");
const { resetRefreshMemory } = await import("@/lib/server/refresh");

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** A platform whose access token `at-old` has expired and whose refresh
 *  route can be held open so several 401s pile up behind it. */
function platform({
  refuse = false,
  offline = false,
}: { refuse?: boolean; offline?: boolean } = {}) {
  const state = { refreshes: 0, calls: [] as string[], release: () => {} };
  const held = new Promise<void>((resolve) => {
    state.release = resolve;
  });
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const bearer = new Headers(init?.headers).get("Authorization") ?? "";
    state.calls.push(`${init?.method ?? "GET"} ${url} ${bearer}`);
    if (url.endsWith("/v1/auth/refresh")) {
      state.refreshes += 1;
      await held;
      if (offline) throw new TypeError("fetch failed");
      if (refuse) return json({ detail: "Refresh token is invalid or expired" }, 401);
      return json({ access_token: "at-new", refresh_token: "rt-new" }, 200);
    }
    if (bearer === "Bearer at-new") {
      if (url.endsWith("/v1/auth/me")) return json({ user: { id: "u1" }, tenant_id: "t1" }, 200);
      return json({ items: [], total: 0 }, 200);
    }
    return json({ detail: "Not authenticated" }, 401);
  });
  vi.stubGlobal("fetch", spy);
  return state;
}

beforeEach(() => {
  cookieStore.jar.clear();
  vi.unstubAllGlobals();
  resetRefreshMemory();
});

describe("the proxy renews the session instead of ending it (WO-73)", () => {
  it("six concurrent 401s cost ONE refresh, and all six get their answer", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, { value: "at-old" });
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform();

    const burst = Array.from({ length: 6 }, (_, i) =>
      proxyGET(
        new Request(`https://portal.example/api/proxy/v1/suppliers?page=${i}`),
        context(["v1", "suppliers"]),
      ),
    );
    // Let every request reach its 401 and queue behind the held refresh.
    await new Promise((r) => setTimeout(r, 10));
    api.release();
    const responses = await Promise.all(burst);

    expect(responses.map((r) => r.status)).toEqual([200, 200, 200, 200, 200, 200]);
    expect(api.refreshes).toBe(1);
    // Six originals with the dead token, one refresh, six replays with the new.
    expect(api.calls.filter((c) => c.endsWith("Bearer at-old")).length).toBe(6);
    expect(api.calls.filter((c) => c.endsWith("Bearer at-new")).length).toBe(6);
    expect(cookieStore.jar.get(ACCESS_COOKIE)?.value).toBe("at-new");
    expect(cookieStore.jar.get(REFRESH_COOKIE)?.value).toBe("rt-new");
  });

  it("a refused refresh ends the session: 401 and both cookies gone", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, { value: "at-old" });
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform({ refuse: true });
    api.release();

    const response = await proxyGET(
      new Request("https://portal.example/api/proxy/v1/suppliers"),
      context(["v1", "suppliers"]),
    );
    expect(response.status).toBe(401);
    expect(await response.json()).toMatchObject({ title: "unauthorized" });
    expect(cookieStore.jar.has(ACCESS_COOKIE)).toBe(false);
    expect(cookieStore.jar.has(REFRESH_COOKIE)).toBe(false);
    expect(api.refreshes).toBe(1);
  });

  it("a network failure during the refresh is offline, not a sign-out", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, { value: "at-old" });
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform({ offline: true });
    api.release();

    const response = await proxyGET(
      new Request("https://portal.example/api/proxy/v1/suppliers"),
      context(["v1", "suppliers"]),
    );
    expect(response.status).toBe(502);
    expect(cookieStore.jar.get(REFRESH_COOKIE)?.value).toBe("rt-old");
    expect(cookieStore.jar.get(ACCESS_COOKIE)?.value).toBe("at-old");
  });

  it("an access cookie the browser already dropped still gets a refresh", async () => {
    // The access cookie's max-age is the token's: after fifteen minutes the
    // browser sends only the refresh cookie. That is not "not signed in".
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform();
    api.release();

    const response = await proxyGET(
      new Request("https://portal.example/api/proxy/v1/suppliers"),
      context(["v1", "suppliers"]),
    );
    expect(response.status).toBe(200);
    expect(api.refreshes).toBe(1);
    expect(cookieStore.jar.get(ACCESS_COOKIE)?.value).toBe("at-new");
  });

  it("with neither cookie it is simply not signed in, and nothing is refreshed", async () => {
    const api = platform();
    const response = await proxyGET(
      new Request("https://portal.example/api/proxy/v1/suppliers"),
      context(["v1", "suppliers"]),
    );
    expect(response.status).toBe(401);
    expect(api.refreshes).toBe(0);
  });
});

describe("the session probe renews too (WO-73)", () => {
  it("a stale tab's first probe comes back authenticated after one refresh", async () => {
    cookieStore.jar.set(ACCESS_COOKIE, { value: "at-old" });
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform();
    api.release();

    const response = await sessionGET();
    expect(await response.json()).toMatchObject({ authenticated: true, tenant_id: "t1" });
    expect(api.refreshes).toBe(1);
    expect(cookieStore.jar.get(ACCESS_COOKIE)?.value).toBe("at-new");
  });

  it("a refused refresh on the probe answers 'nobody' and clears the cookies", async () => {
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform({ refuse: true });
    api.release();

    const response = await sessionGET();
    expect(await response.json()).toEqual({ authenticated: false });
    expect(cookieStore.jar.has(REFRESH_COOKIE)).toBe(false);
  });

  it("a probe and six data requests at once still cost one refresh", async () => {
    cookieStore.jar.set(REFRESH_COOKIE, { value: "rt-old" });
    const api = platform();
    const all = [
      sessionGET(),
      ...Array.from({ length: 6 }, () =>
        proxyGET(
          new Request("https://portal.example/api/proxy/v1/suppliers"),
          context(["v1", "suppliers"]),
        ),
      ),
    ];
    await new Promise((r) => setTimeout(r, 10));
    api.release();
    const responses = await Promise.all(all);
    expect(responses.map((r) => r.status)).toEqual([200, 200, 200, 200, 200, 200, 200]);
    expect(api.refreshes).toBe(1);
  });
});
