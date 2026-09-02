/**
 * Suppliers and collection centres (DEMO-003).
 *
 * These pages move money indirectly — a supplier activated without a centre
 * cannot be paid, and a centre that looks READY when it is not will turn milk
 * away at the gate. So the tests below check the two things that matter most:
 * that filtering happens on the SERVER, and that a refusal from the platform
 * is repeated to the operator rather than swallowed or reworded.
 */
import { Suspense } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

import CenterDetailPage from "@/app/centers/[id]/page";
import CentersPage from "@/app/centers/page";
import SupplierDetailPage from "@/app/suppliers/[id]/page";
import SuppliersPage from "@/app/suppliers/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const CENTER = {
  id: "c1",
  branch_id: "b1",
  name: "Kilima Hill Collection Centre",
  code: "KH-C1",
  status: "active",
  timezone: "Africa/Nairobi",
};

const SUPPLIER = {
  id: "s1",
  code: "S-001",
  status: "draft",
  branch_id: null,
  full_name: "Amina Njoroge",
  phone: "+254700000001",
};

const CENTER_ACTIVITY = {
  items: [
    {
      center_id: "c1",
      center_code: "KH-C1",
      center_name: "Kilima Hill Collection Centre",
      transactions: 40,
      accepted: 39,
      total_net_weight_kg: 1234.5,
      payable_amount: "56789.50",
      currency: "KES",
      weighted_avg_fat: 4.2,
      last_collection_at: "2026-08-10T07:30:00+00:00",
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

const SUPPLIER_ACTIVITY = {
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
      last_collection_at: "2026-08-10T07:30:00+00:00",
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

const DAILY = {
  date_from: "2026-07-13",
  date_to: "2026-08-11",
  transactions: 40,
  accepted: 39,
  rejected: 1,
  cancelled: 0,
  in_progress: 0,
  suppliers_served: 18,
  total_net_weight_kg: 1234.5,
  payable_by_currency: { KES: "56789.50" },
  unpriced_accepted: 0,
  weighted_avg_fat: 4.21,
  weighted_avg_snf: 8.6,
};

const TREND = {
  date_from: "2026-08-10",
  date_to: "2026-08-11",
  points: [
    {
      day: "2026-08-10",
      transactions: 4,
      accepted: 4,
      total_net_weight_kg: 120,
      payable_amount: "5460.00",
      currency: "KES",
    },
    {
      day: "2026-08-11",
      transactions: 0,
      accepted: 0,
      total_net_weight_kg: 0,
      payable_amount: "0",
      currency: null,
    },
  ],
};

const READINESS = {
  center_id: "c1",
  status: "NOT_READY",
  evaluated_at: "2026-08-11T09:00:00+00:00",
  checks: [
    { rule: "operating_hours", severity: "blocking", passed: true, detail: "" },
    {
      rule: "active_scale",
      severity: "blocking",
      passed: false,
      detail: "no active scale is assigned to this centre",
    },
  ],
};

const EMPTY_PAGE = { items: [], total: 0, limit: 10, offset: 0 };

function routeAll(overrides: Record<string, () => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    void init;
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/reports/collection/by-center"))
      return json(CENTER_ACTIVITY);
    if (url.includes("/reports/collection/by-supplier"))
      return json(SUPPLIER_ACTIVITY);
    if (url.includes("/reports/collection/daily")) return json(DAILY);
    if (url.includes("/reports/collection/trend")) return json(TREND);
    if (url.includes("/reports/settlements"))
      return json({
        by_status: [],
        finalized_by_currency: {},
        total_settlements: 0,
        total_lines: 0,
      });
    if (url.includes("/reports/payments"))
      return json({
        by_status: [],
        total_payments: 0,
        completed_count: 0,
        processing_count: 0,
        pending_count: 0,
        failed_count: 0,
        completed_by_currency: {},
        outstanding_by_currency: {},
        failed_by_currency: {},
        total_by_currency: {},
      });
    if (url.includes("/collection-centers/c1/readiness"))
      return json(READINESS);
    if (url.includes("/collection-centers/c1"))
      return json({
        center: CENTER,
        settings: {},
        operating_windows: [
          { day_of_week: 1, opens: "06:00", closes: "19:00" },
        ],
        calendar: [],
      });
    if (url.includes("/collection-centers"))
      return json({ items: [CENTER], total: 1, limit: 10, offset: 0 });
    if (url.includes("/v1/branches"))
      return json([
        { id: "b1", workspace_id: "w1", name: "Central", code: "C" },
      ]);
    if (url.includes("/v1/suppliers/s1"))
      return json({
        supplier: SUPPLIER,
        profile: {
          full_name: "Amina Njoroge",
          phone: "+254700000001",
          village: "Kilima",
          national_id: "",
        },
        center_ids: [],
        bank_accounts: [],
        documents: [],
      });
    if (url.includes("/v1/suppliers"))
      return json({ items: [SUPPLIER], total: 1, limit: 10, offset: 0 });
    if (url.includes("/milk-transactions")) return json(EMPTY_PAGE);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

/**
 * Detail pages read their route parameters with React's `use()`, which
 * SUSPENDS until the promise settles. Without a boundary React renders nothing
 * and every query times out against an empty document — which is exactly what
 * the first draft of these tests did. The app has one (Next provides it); the
 * test must supply its own.
 */
const renderDetail = async (ui: React.ReactElement) => {
  // `act` lets the microtask that settles the params promise run BEFORE the
  // assertions start, so React retries the suspended render instead of leaving
  // the fallback on screen for the whole timeout.
  await act(async () => {
    render(<Suspense fallback={<span>loading route…</span>}>{ui}</Suspense>);
  });
};

/**
 * The alert that says something in particular (LACTEVA-QA-004).
 *
 * `findByRole("alert")` asks for THE alert, and these pages have several
 * regions that load and fail on their own — every `ErrorState` is also
 * `role="alert"`. When a neighbour is still showing one, `findByRole` throws
 * "Found multiple elements", which is the flake QA-003 traced on
 * `transactions/[id]` after three cycles of blaming the hardware.
 *
 * `role="alert"` is not a name-from-content role and cannot be selected by
 * `name`, so the alert is found by what it SAYS. This is stronger than the
 * bare selector it replaces: that one required exactly one alert anywhere and
 * that it happened to say this; this requires an alert that says it.
 */
async function alertSaying(pattern: RegExp): Promise<HTMLElement> {
  return waitFor(() => {
    const found = screen
      .getAllByRole("alert")
      .find((el) => pattern.test(el.textContent ?? ""));
    if (!found) throw new Error(`no alert yet matching ${pattern}`);
    return found;
  });
}

describe("centres list", () => {
  it("shows each centre with the activity the platform aggregated", async () => {
    routeAll();
    render(<CentersPage />);
    expect(
      await screen.findByText("Kilima Hill Collection Centre"),
    ).toBeInTheDocument();
    expect(screen.getByText("KH-C1")).toBeInTheDocument();
    expect(screen.getByText("1,234.5")).toBeInTheDocument();
    expect(screen.getByText("56,789.50")).toBeInTheDocument();
    expect(screen.getByText("2026-08-10")).toBeInTheDocument();
  });

  it("sends search and status to the SERVER rather than filtering in the browser", async () => {
    const spy = routeAll();
    render(<CentersPage />);
    await screen.findByText("Kilima Hill Collection Centre");

    await userEvent.type(screen.getByLabelText("Search"), "kilima");
    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/v1/collection-centers?"));
      expect(asked.some((u) => u.includes("q=kilima"))).toBe(true);
    });

    await userEvent.selectOptions(screen.getByLabelText("Status"), "active");
    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/v1/collection-centers?"));
      expect(asked.some((u) => u.includes("status=active"))).toBe(true);
    });
  });

  it("explains an empty search rather than showing a bare 'no data'", async () => {
    routeAll({ "/v1/collection-centers?": () => json(EMPTY_PAGE) });
    render(<CentersPage />);
    expect(
      await screen.findByText(/no collection centres yet/i),
    ).toBeInTheDocument();
  });

  it("shows an error with a retry when the list fails", async () => {
    routeAll({
      "/v1/collection-centers?": () => json({ detail: "boom" }, 500),
    });
    render(<CentersPage />);
    // The platform's own word for what went wrong, which is what this page
    // promises to show rather than a generic sentence of its own.
    expect(await alertSaying(/boom/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("validates the form before asking the platform", async () => {
    const spy = routeAll();
    render(<CentersPage />);
    await screen.findByText("Kilima Hill Collection Centre");

    await userEvent.click(screen.getByRole("button", { name: /new centre/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /create centre/i }),
    );

    expect(
      await screen.findByText(/name of at least 2 characters/i),
    ).toBeInTheDocument();
    // Nothing was posted: an invalid form must not reach the platform.
    const posts = spy.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(0);
  });

  it("links each centre to its own page", async () => {
    routeAll();
    render(<CentersPage />);
    const link = await screen.findByRole("link", {
      name: "Kilima Hill Collection Centre",
    });
    expect(link).toHaveAttribute("href", "/centers/c1");
  });
});

describe("centre detail", () => {
  const params = () => Promise.resolve({ id: "c1" });

  it("shows the platform's readiness verdict with the reason each check failed", async () => {
    routeAll();
    await renderDetail(<CenterDetailPage params={params()} />);

    // Not a green badge inferred from the record existing.
    expect(await screen.findByText("not ready")).toBeInTheDocument();
    expect(
      screen.getByText(/no active scale is assigned to this centre/i),
    ).toBeInTheDocument();
    expect(screen.getByText("active scale")).toBeInTheDocument();
  });

  it("shows operating hours, statistics and the trend", async () => {
    routeAll();
    await renderDetail(<CenterDetailPage params={params()} />);
    expect(await screen.findByText("Monday")).toBeInTheDocument();
    expect(screen.getByText("06:00 – 19:00")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("1,234.5")).toBeInTheDocument(),
    );
    expect(screen.getByText("56,789.50")).toBeInTheDocument();
  });

  it("warns when a centre has no operating hours at all", async () => {
    // Overrides match in order: keep readiness normal, then answer the detail
    // request (which carries no query string) with a centre that has no hours.
    routeAll({
      "/collection-centers/c1/readiness": () => json(READINESS),
      "/collection-centers/c1": () =>
        json({
          center: CENTER,
          settings: {},
          operating_windows: [],
          calendar: [],
        }),
    });
    await renderDetail(<CenterDetailPage params={params()} />);
    expect(
      await screen.findByText(/a centre without operating hours cannot open/i),
    ).toBeInTheDocument();
  });

  it("survives every panel failing at once", async () => {
    routeAll({
      "/reports/": () => json({ detail: "down" }, 500),
      "/collection-centers/c1/readiness": () => json({ detail: "down" }, 500),
    });
    await renderDetail(<CenterDetailPage params={params()} />);
    // The page still renders; the failing cards say so individually.
    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
  });
});

describe("suppliers list", () => {
  it("shows suppliers with aggregated activity", async () => {
    routeAll();
    render(<SuppliersPage />);
    expect(await screen.findByText("Amina Njoroge")).toBeInTheDocument();
    expect(screen.getByText("240.5")).toBeInTheDocument();
    expect(screen.getByText("10,942.75")).toBeInTheDocument();
  });

  it("filters by centre on the server", async () => {
    const spy = routeAll();
    render(<SuppliersPage />);
    await screen.findByText("Amina Njoroge");

    await userEvent.selectOptions(screen.getByLabelText("Centre"), "c1");
    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/v1/suppliers?"));
      expect(asked.some((u) => u.includes("center_id=c1"))).toBe(true);
    });
  });

  it("repeats the platform's refusal when activation is not allowed", async () => {
    // BR: a supplier must be assigned to a collection centre before activation.
    routeAll({
      "/v1/suppliers/s1/status": () =>
        json(
          {
            title: "conflict",
            detail:
              "cannot activate a supplier without a collection center assignment",
            status: 409,
          },
          409,
        ),
    });
    render(<SuppliersPage />);
    await screen.findByText("Amina Njoroge");

    await userEvent.click(screen.getByRole("button", { name: /activate/i }));

    // The platform's own words, not a guess at the reason.
    expect(
      await screen.findByText(/without a collection center assignment/i),
    ).toBeInTheDocument();
  });

  it("links each supplier to its own page", async () => {
    routeAll();
    render(<SuppliersPage />);
    const link = await screen.findByRole("link", { name: "Amina Njoroge" });
    expect(link).toHaveAttribute("href", "/suppliers/s1");
  });
});

describe("supplier detail", () => {
  const params = () => Promise.resolve({ id: "s1" });

  it("shows the profile and the platform's statistics", async () => {
    routeAll();
    await renderDetail(<SupplierDetailPage params={params()} />);
    expect(
      await screen.findByRole("heading", { name: "Amina Njoroge" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("1,234.5")).toBeInTheDocument(),
    );
    expect(screen.getByText("56,789.50")).toBeInTheDocument();
  });

  it("says why a draft supplier cannot be activated yet", async () => {
    routeAll();
    await renderDetail(<SupplierDetailPage params={params()} />);
    expect(
      await screen.findByText(/not assigned to a collection centre yet/i),
    ).toBeInTheDocument();
  });

  it("shows an empty state for a supplier with no payments", async () => {
    routeAll();
    await renderDetail(<SupplierDetailPage params={params()} />);
    expect(await screen.findByText(/no payments yet/i)).toBeInTheDocument();
  });

  it("explains a supplier that cannot be loaded, and offers the way back", async () => {
    routeAll({ "/v1/suppliers/s1": () => json({ detail: "gone" }, 404) });
    await renderDetail(<SupplierDetailPage params={params()} />);
    const alert = await alertSaying(/could not be loaded/i);
    expect(within(alert).getByText(/could not be loaded/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /back to suppliers/i }),
    ).toBeInTheDocument();
  });
});
