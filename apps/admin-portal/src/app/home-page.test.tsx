/**
 * The dashboard (DASH-001, extended by DEMO-002).
 *
 * DASH-001: `refresh()` fetched /health/ready and cast the body without
 * checking the status. A 401 answers with a problem document — no `checks` —
 * so the render reached `Object.entries(undefined)` and threw, taking the
 * whole page down. A cast is a claim, not a check.
 *
 * DEMO-002 rebuilt this page on the platform's `/v1/reports/*` aggregates and
 * dropped the platform-health card, which belongs on Operations rather than on
 * a customer's dashboard. The GUARANTEE is unchanged and is what the tests
 * below defend: never crash on a body that is missing fields, ask for nothing
 * tenant-scoped while signed out, and let one failed widget cost only itself.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

import Home from "@/app/page";

const USER = {
  id: "u1",
  email: "boss@kilima.example",
  full_name: "Boss",
  locale: "en",
  is_active: true,
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const SESSION = { authenticated: true, user: USER, tenant_id: "org-1", permissions: ["*"] };

/** A complete, realistic dashboard payload — the shape the platform sends. */
const DASHBOARD = {
  date_from: "2026-08-05",
  date_to: "2026-08-11",
  collection: {
    date_from: "2026-08-05",
    date_to: "2026-08-11",
    transactions: 42,
    accepted: 40,
    rejected: 2,
    cancelled: 0,
    in_progress: 0,
    suppliers_served: 18,
    total_net_weight_kg: 1234.5,
    payable_by_currency: { KES: "56789.50" },
    unpriced_accepted: 0,
    weighted_avg_fat: 4.21,
    weighted_avg_snf: 8.6,
  },
  settlements: {
    by_status: [{ status: "finalized", count: 5, net_amount: "12345.00" }],
    finalized_net_total: "12345.00",
    total_settlements: 5,
    total_lines: 40,
  },
  payments: {
    by_status: [{ status: "completed", count: 3, amount: "9000.00", currency: "KES" }],
    total_payments: 4,
    completed_count: 3,
    processing_count: 0,
    pending_count: 0,
    failed_count: 1,
    completed_amount: "9000.00",
    outstanding_amount: "0.00",
    failed_amount: "1500.00",
    total_by_currency: { KES: "10500.00" },
  },
  rate_bands: [
    {
      unit_price: "45.5000",
      currency: "KES",
      transactions: 20,
      total_net_weight_kg: 700,
      payable_amount: "31850.00",
    },
  ],
  active_suppliers: 24,
  active_centers: 5,
  inactive_centers: 0,
  attention: [],
};

const TREND = {
  date_from: "2026-08-05",
  date_to: "2026-08-06",
  points: [
    {
      day: "2026-08-05",
      transactions: 10,
      accepted: 10,
      total_net_weight_kg: 300,
      payable_amount: "13650.00",
      currency: "KES",
    },
    {
      day: "2026-08-06",
      transactions: 0,
      accepted: 0,
      total_net_weight_kg: 0,
      payable_amount: "0",
      currency: null,
    },
  ],
};

const CENTERS = {
  items: [
    {
      center_id: "c1",
      center_code: "KH-C1",
      center_name: "Kilima Hill Collection Centre",
      transactions: 20,
      accepted: 20,
      total_net_weight_kg: 640.25,
      payable_amount: "29131.38",
      currency: "KES",
      weighted_avg_fat: 4.3,
    },
  ],
  total: 1,
  limit: 8,
  offset: 0,
};

const SUPPLIERS = {
  items: [
    {
      supplier_id: "s1",
      supplier_code: "S-001",
      supplier_name: "Amina Njoroge",
      deliveries: 12,
      accepted: 12,
      total_net_weight_kg: 240.5,
      payable_amount: "10942.75",
      currency: "KES",
      weighted_avg_fat: 4.2,
    },
  ],
  total: 1,
  limit: 8,
  offset: 0,
};

// DEMO-007 made /v1/audit a page like every other list on the platform.
const AUDIT = {
  items: [
    {
      id: "a1",
      action: "settlement.finalized",
      resource_type: "settlement",
      resource_id: "x",
      actor_id: "u1",
      request_id: null,
      created_at: "2026-08-11T09:30:00+00:00",
      detail: {},
    },
  ],
  total: 1,
  limit: 12,
  offset: 0,
};

/** Route every request the dashboard makes; `overrides` replaces one of them. */
function routeAll(overrides: Record<string, () => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/api/auth/session")) return json(SESSION);
    if (url.includes("/reports/dashboard")) return json(DASHBOARD);
    if (url.includes("/reports/collection/trend")) return json(TREND);
    if (url.includes("/reports/collection/by-center")) return json(CENTERS);
    if (url.includes("/reports/collection/by-supplier")) return json(SUPPLIERS);
    if (url.includes("/v1/audit")) return json(AUDIT);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("dashboard", () => {
  it("does not crash when the platform answers 401 to everything", async () => {
    routeAll({
      "/api/auth/session": () => json({ authenticated: false }),
      "/v1/": () => json({ title: "unauthorized", status: 401 }, 401),
    });

    // Rendering at all is the assertion: the old build threw here.
    render(<Home />);
    expect(await screen.findByText(/sign in to see today/i)).toBeInTheDocument();
  });

  it("asks for nothing tenant-scoped while signed out", async () => {
    const spy = routeAll({ "/api/auth/session": () => json({ authenticated: false }) });

    render(<Home />);
    await screen.findByText(/sign in to see today/i);
    await new Promise((r) => setTimeout(r, 50));

    const asked = spy.mock.calls.map(([u]) => String(u));
    expect(asked.some((u) => u.includes("/reports/"))).toBe(false);
    expect(asked.some((u) => u.includes("/v1/audit"))).toBe(false);
  });

  it("renders every aggregate from the platform's own figures", async () => {
    routeAll();
    render(<Home />);

    // Collection KPIs.
    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText("1,234.5")).toBeInTheDocument();
    expect(screen.getByText("56,789.50")).toBeInTheDocument();
    expect(screen.getByText("4.21%")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();

    // Settlement and payment figures.
    await waitFor(() => expect(screen.getByText("12,345.00")).toBeInTheDocument());
    expect(screen.getByText("9,000.00")).toBeInTheDocument();

    // Centre, supplier and activity sections.
    expect(screen.getByText("Kilima Hill Collection Centre")).toBeInTheDocument();
    expect(screen.getByText("Amina Njoroge")).toBeInTheDocument();
    expect(screen.getByText(/settlement finalized/)).toBeInTheDocument();
  });

  it("says 'not part of your access' rather than showing an error, on a 403", async () => {
    /**
     * DEMO-008. A collection operator has no `reporting.read`, so every
     * aggregate on this page 403s for them. Rendering that as a wall of red
     * errors tells them something broke, when the truth is that reporting is
     * not part of their job — and an operator who believes the platform is
     * broken raises a support ticket instead of getting on with their work.
     */
    routeAll({
      "/v1/reports/": () =>
        json({ title: "forbidden", detail: "You do not have permission to perform this action." }, 403),
    });
    render(<Home />);

    expect(await screen.findByText("Reporting is not part of your access.")).toBeInTheDocument();
    // The same reassurance appears on each section that could not load.
    expect(screen.getAllByText(/nothing here is broken/i).length).toBeGreaterThan(0);
    // ...and NOT the failure wording.
    expect(screen.queryByText(/could not be loaded/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("still reports a genuine failure as a failure", async () => {
    routeAll({ "/v1/reports/dashboard": () => json({ title: "boom", detail: "boom" }, 500) });
    render(<Home />);
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
  });

  it("formats money with grouping and keeps the platform's decimals", async () => {
    routeAll();
    render(<Home />);
    // 56789.50 -> 56,789.50 with no rounding and no float round-trip.
    expect(await screen.findByText("56,789.50")).toBeInTheDocument();
    expect(screen.getAllByText("KES").length).toBeGreaterThan(0);
    // The rate band keeps four decimal places, because a unit price has them.
    expect(screen.getByText(/45\.5000 KES \/ kg/)).toBeInTheDocument();
  });

  it("shows a loading state before anything has answered", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<Home />);
    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
  });

  it("shows an empty state rather than a broken chart when nothing was collected", async () => {
    routeAll({
      "/reports/collection/trend": () =>
        json({ date_from: "2026-08-05", date_to: "2026-08-05", points: [] }),
    });
    render(<Home />);
    expect(await screen.findByText(/no collection in this period/i)).toBeInTheDocument();
  });

  it("reports 'no action required' when there are no exceptions", async () => {
    routeAll();
    render(<Home />);
    expect(await screen.findByText(/no action required/i)).toBeInTheDocument();
  });

  it("surfaces real exceptions with their counts and a way to act", async () => {
    routeAll({
      "/reports/dashboard": () =>
        json({
          ...DASHBOARD,
          attention: [
            {
              key: "failed_payments",
              label: "payments failed and need retrying",
              count: 2,
              severity: "critical",
              href: "/payments",
            },
          ],
        }),
    });
    render(<Home />);
    expect(await screen.findByText(/payments failed and need retrying/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review/i })).toHaveAttribute("href", "/payments");
  });

  it("survives a response that is 200 but missing the fields it claims", async () => {
    // The DEMO-001 lesson, kept: `{}` must not reach `.map` and crash the page.
    routeAll({
      "/reports/dashboard": () => json({}),
      "/reports/collection/trend": () => json({}),
      "/reports/collection/by-center": () => json({}),
      "/reports/collection/by-supplier": () => json({}),
      "/v1/audit": () => json({}),
    });
    render(<Home />);
    // The page still renders its structure instead of throwing.
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("lets one failed widget cost only itself", async () => {
    routeAll({ "/reports/collection/by-center": () => json({ detail: "boom" }, 500) });
    render(<Home />);

    // The failing card explains itself...
    expect(await screen.findByText(/centre performance is unavailable/i)).toBeInTheDocument();
    // ...while every other region still shows its data.
    expect(screen.getByText("56,789.50")).toBeInTheDocument();
    expect(screen.getByText("Amina Njoroge")).toBeInTheDocument();
  });

  it("asks the BACKEND for a new window when the date range changes", async () => {
    const spy = routeAll();
    render(<Home />);
    await screen.findByText("42");

    await userEvent.click(screen.getByRole("button", { name: "Today" }));

    await waitFor(() => {
      const dashboardCalls = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/reports/dashboard"));
      const last = dashboardCalls[dashboardCalls.length - 1];
      // Same day both ends — and sent as query parameters, so the aggregation
      // happens in the database rather than over rows fetched into the browser.
      const from = new URL(last, "http://x").searchParams.get("date_from");
      const to = new URL(last, "http://x").searchParams.get("date_to");
      expect(from).toBe(to);
      expect(from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  it("sends the same window to every aggregate, so the page cannot disagree with itself", async () => {
    const spy = routeAll();
    render(<Home />);
    await screen.findByText("42");

    const windows = spy.mock.calls
      .map(([u]) => String(u))
      .filter((u) => u.includes("/reports/"))
      .map((u) => {
        const params = new URL(u, "http://x").searchParams;
        return `${params.get("date_from")}..${params.get("date_to")}`;
      });
    expect(windows.length).toBeGreaterThan(1);
    expect(new Set(windows).size).toBe(1);
  });
});
