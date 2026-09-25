/**
 * No page fetches itself in a loop (WO-95).
 *
 * The Month sheet shipped green and then made 1,548 requests in 25 seconds
 * on live, until nginx's per-client limiter answered 503 to every page that
 * person opened next. A page-by-page suite is structurally bad at seeing a
 * render loop: every test asserts WHAT was fetched, and a loop fetches the
 * right thing, again and again. So this renders EVERY page component with
 * the network refusing (a 404 problem for everything — a loop that fires on
 * error is a loop), lets it settle, and counts. A page that legitimately
 * asks a dozen questions on open is fine; one that asks sixty a second is
 * not, and this is where it fails.
 *
 * WHAT THIS DOES NOT SEE, said plainly: a loop that only runs on the SUCCESS
 * path. WO-95's own loop was one — with the sheet refused, the error path
 * damped to four requests and this guard passed against the broken page,
 * verified before it was trusted. Exercising every page's success path needs
 * every page's fixtures, which is each page's own suite; the assertion that
 * belongs there is the one `month-sheet.test.tsx` now carries — count the
 * calls after settling OUTSIDE `act`. This file keeps the other half: no
 * page loops on a refusal, on any of the 48.
 */
import { Suspense } from "react";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "x", token: "t" }),
  notFound: () => {
    throw new Error("notFound");
  },
}));

const pages = import.meta.glob("./**/page.tsx");

/** More than this in the settle window is a loop, not a busy page. */
const CEILING = 30;

/**
 * Let the page run UNATTENDED for a while. Inside `act`, React holds every
 * effect until the block exits, so a loop advances exactly one turn per act
 * and looks like a single extra request — which is how the 1,548-request
 * loop hid from a count taken inside `act`. Outside it, the page behaves as
 * it does in a browser.
 */
async function settle(ms: number) {
  const g = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const was = g.IS_REACT_ACT_ENVIRONMENT;
  g.IS_REACT_ACT_ENVIRONMENT = false;
  try {
    await new Promise((r) => setTimeout(r, ms));
  } finally {
    g.IS_REACT_ACT_ENVIRONMENT = was;
  }
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("no page fetches itself in a loop", () => {
  it.each(Object.keys(pages).sort())("%s settles", async (path) => {
    // A signed-in session with every permission and a business timezone, so a
    // page gets past its shell and asks its real questions; everything else
    // is refused. (With the session itself refused, the Month sheet's loop
    // never started — `today` stayed null — and the guard saw nothing.)
    const session = {
      authenticated: true,
      acting_tenant_id: null,
      user: { id: "u1", email: "a@b.example", full_name: "A", locale: "en", is_active: true },
      tenant_id: "org-1",
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        country_code: "IN",
        currency_code: "INR",
        currency_symbol: "₹",
        timezone: "Asia/Kolkata",
        default_language: "en",
        supported_languages: ["en"],
        languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
        quantity_unit: "litre",
        quantity_unit_label: "L",
        modules: ["collection", "sales"],
      },
      membership: null,
      roles: [],
      center_scope: null,
      permissions: ["*"],
    };
    const spy = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/auth/session") || url.includes("/v1/auth/me"))
        return new Response(JSON.stringify(session), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      return new Response(JSON.stringify({ title: "not_found", detail: "no" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", spy);
    vi.stubGlobal("location", { assign: vi.fn(), replace: vi.fn(), reload: vi.fn(), pathname: "/", href: "http://portal.example/", search: "" });
    const mod = (await pages[path]()) as { default: React.ComponentType<Record<string, unknown>> };
    const Page = mod.default;
    const params = Promise.resolve({ id: "00000000-0000-0000-0000-000000000000", token: "t" });
    await act(async () => {
      render(
        <Suspense fallback={null}>
          <Page params={params} />
        </Suspense>,
      );
    });
    await settle(600);
    expect(
      spy.mock.calls.length,
      `${path} made ${spy.mock.calls.length} requests in the settle window`,
    ).toBeLessThanOrEqual(CEILING);
  });
});
