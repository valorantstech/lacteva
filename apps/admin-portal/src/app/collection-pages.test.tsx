/**
 * Collections list and detail (DEMO-004).
 *
 * The detail page is the strongest screen in the demonstration and the one
 * with the most ways to lie, so the tests below defend the two things that
 * make it honest:
 *
 *   the pricing breakdown is PRINTED, never recomputed; and
 *   the timeline shows what happened, with everything else marked pending.
 */
import { Suspense } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/transactions",
}));

import TransactionDetailPage from "@/app/transactions/[id]/page";
import TransactionsPage from "@/app/transactions/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** The canonical demo collection: 10.000 kg at 45.0000 = 450.00 KES. */
const TX = {
  id: "tx-1",
  session_id: "se-1",
  center_id: "c1",
  supplier_id: "s1",
  operator_id: "u1",
  state: "COMPLETED",
  milk_type: "cow",
  container_type: "can",
  container_identifier: "CAN-01",
  weight_unit: "kg",
  gross_weight: 12,
  tare_weight: 2,
  net_weight: 10,
  fat: 4.2,
  snf: 8.6,
  clr: 28.5,
  density: null,
  pricing_status: "priced",
  unit_price: "45.0000",
  gross_amount: "450.00",
  currency: "KES",
  calculation_id: "calc-1",
  pricing_detail: "RC-2026-MAIN v1 band [4.0, 5.0)",
  rejected_reason: null,
  created_at: "2026-08-10T07:30:00+00:00",
  completed_at: "2026-08-10T07:45:00+00:00",
};

const EVENTS = [
  { sequence: 1, event_type: "TransactionCreated", data: {}, created_at: "2026-08-10T07:30:00+00:00" },
  { sequence: 2, event_type: "SupplierIdentified", data: {}, created_at: "2026-08-10T07:31:00+00:00" },
  { sequence: 3, event_type: "WeightCaptured", data: {}, created_at: "2026-08-10T07:33:00+00:00" },
  { sequence: 4, event_type: "PricingCompleted", data: {}, created_at: "2026-08-10T07:35:00+00:00" },
  { sequence: 5, event_type: "TransactionCompleted", data: {}, created_at: "2026-08-10T07:45:00+00:00" },
];

const CHAIN = {
  transaction_id: "tx-1",
  settlement: {
    id: "st-1",
    settlement_number: "STL-2026-000004",
    status: "finalized",
    period_from: "2026-08-11",
    period_to: "2026-08-11",
    currency: "KES",
    gross_amount: "3600.00",
    adjustments_amount: "0.00",
    net_amount: "3600.00",
    line_amount: "450.00",
    finalized_at: "2026-08-11T09:00:00+00:00",
  },
  payment: {
    id: "pa-1",
    payment_number: "PAY-2026-000004",
    status: "completed",
    method: "MOBILE_MONEY",
    currency: "KES",
    amount: "3600.00",
    allocated_amount: "450.00",
    reference: "MPESA-DEMO",
    paid_at: "2026-08-11T09:05:00+00:00",
  },
  receipt: {
    id: "rc-1",
    receipt_number: "RCP-2026-000004",
    status: "generated",
    net_amount: "3600.00",
    currency: "KES",
    generated_at: "2026-08-11T09:05:30+00:00",
  },
};

const DAILY = {
  date_from: "2026-07-13",
  date_to: "2026-08-11",
  transactions: 351,
  accepted: 350,
  rejected: 1,
  cancelled: 0,
  in_progress: 0,
  suppliers_served: 24,
  total_net_weight_kg: 7868,
  payable_by_currency: { KES: "353234.00" },
  unpriced_accepted: 0,
  weighted_avg_fat: 4.3,
  weighted_avg_snf: 8.5,
};

function routeAll(overrides: Record<string, () => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/reports/collection/daily")) return json(DAILY);
    if (url.includes("/chain")) return json(CHAIN);
    if (url.includes("/milk-transactions/tx-1/events")) return json(EVENTS);
    if (url.includes("/milk-transactions/tx-1")) return json(TX);
    if (url.includes("/milk-transactions"))
      return json({ items: [TX], total: 1, limit: 15, offset: 0 });
    if (url.includes("/collection-centers"))
      return json({
        items: [{ id: "c1", branch_id: "b1", name: "Kilima Hill", code: "KH-C1", status: "active", timezone: "Africa/Nairobi" }],
        total: 1, limit: 100, offset: 0,
      });
    if (url.includes("/v1/suppliers"))
      return json({
        items: [{ id: "s1", code: "S-001", status: "active", branch_id: null, full_name: "Amina Njoroge", phone: "+254700000001" }],
        total: 1, limit: 100, offset: 0,
      });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

const renderDetail = async (ui: React.ReactElement) => {
  // Route params arrive through `use()`, which suspends; the promise must
  // settle inside `act` or every query runs against an empty document.
  await act(async () => {
    render(<Suspense fallback={<span>loading route…</span>}>{ui}</Suspense>);
  });
};

describe("collections list", () => {
  it("shows collections with the platform's own figures", async () => {
    routeAll();
    render(<TransactionsPage />);
    expect(await screen.findByText("2026-08-10")).toBeInTheDocument();
    expect(screen.getByText("450.00")).toBeInTheDocument();
    // DEMO-007 moved the rate under the value it produced. It is still the
    // platform's exact four-decimal string, ungrouped.
    expect(screen.getByText("@ 45.0000")).toBeInTheDocument();
    // KPI row comes from the reporting aggregate, not from counting rows.
    expect(screen.getByText("351")).toBeInTheDocument();
    expect(screen.getByText("353,234.00")).toBeInTheDocument();
  });

  it("sends the date window and every filter to the SERVER", async () => {
    const spy = routeAll();
    render(<TransactionsPage />);
    await screen.findByText("2026-08-10");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "COMPLETED");
    await userEvent.selectOptions(screen.getByLabelText("Centre"), "c1");
    await userEvent.selectOptions(screen.getByLabelText("Supplier"), "s1");

    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/milk-transactions?"));
      const last = asked[asked.length - 1];
      const q = new URL(last, "http://x").searchParams;
      expect(q.get("state")).toBe("COMPLETED");
      expect(q.get("center_id")).toBe("c1");
      expect(q.get("supplier_id")).toBe("s1");
      // The window is a query parameter — the database narrows, not the browser.
      expect(q.get("date_from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(q.get("date_to")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  it("offers a way back once filters are applied", async () => {
    routeAll();
    render(<TransactionsPage />);
    await screen.findByText("2026-08-10");
    expect(screen.queryByRole("button", { name: /clear filters/i })).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "COMPLETED");
    expect(await screen.findByRole("button", { name: /clear filters/i })).toBeInTheDocument();
  });

  it("says the filters are the reason when nothing matches", async () => {
    routeAll({ "/milk-transactions?": () => json({ items: [], total: 0, limit: 15, offset: 0 }) });
    render(<TransactionsPage />);
    expect(await screen.findByText(/no collections in this period/i)).toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    routeAll({ "/milk-transactions?": () => json({ detail: "boom" }, 500) });
    render(<TransactionsPage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("collection detail", () => {
  const params = () => Promise.resolve({ id: "tx-1" });

  it("PRINTS the pricing calculation rather than recomputing it", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);

    // The three operands the platform sent, shown as an expression.
    expect(await screen.findByText("10 × 45.0000")).toBeInTheDocument();
    expect(screen.getByText("= 450.00 KES")).toBeInTheDocument();
    // The band that resolved it.
    expect(screen.getByText(/RC-2026-MAIN v1 band \[4\.0, 5\.0\)/)).toBeInTheDocument();
    // Trailing zeros on a four-decimal unit price survive, in both the rate
    // row and the printed expression.
    expect(screen.getAllByText(/45\.0000/).length).toBeGreaterThanOrEqual(2);
  });

  it("shows the real event trail from the platform", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(await screen.findByText("Transaction created")).toBeInTheDocument();
    expect(screen.getByText("Supplier identified")).toBeInTheDocument();
    expect(screen.getByText("Pricing completed")).toBeInTheDocument();
    expect(screen.getByText("Transaction completed")).toBeInTheDocument();
  });

  it("follows the money to settlement, payment and receipt", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(await screen.findByText("STL-2026-000004")).toBeInTheDocument();
    expect(screen.getByText("PAY-2026-000004")).toBeInTheDocument();
    expect(screen.getByText("RCP-2026-000004")).toBeInTheDocument();
    // What THIS collection contributed, distinct from the settlement total.
    expect(screen.getAllByText("450.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3,600.00").length).toBeGreaterThan(0);
  });

  it("marks stages that have not happened as pending, never as done", async () => {
    routeAll({
      "/chain": () =>
        json({ transaction_id: "tx-1", settlement: null, payment: null, receipt: null }),
    });
    await renderDetail(<TransactionDetailPage params={params()} />);

    expect(await screen.findByText(/has not been settled yet/i)).toBeInTheDocument();
    expect(screen.getByText(/payment follows settlement/i)).toBeInTheDocument();
    expect(screen.getByText(/receipt follows payment/i)).toBeInTheDocument();
    // The timeline says pending rather than inventing a completion.
    expect(screen.getAllByText("pending").length).toBeGreaterThanOrEqual(4);
  });

  it("says a collection is not priced rather than showing a zero", async () => {
    // Events first: `/milk-transactions/tx-1` would otherwise also swallow
    // `/milk-transactions/tx-1/events` and hand the timeline an object.
    routeAll({
      "/milk-transactions/tx-1/events": () => json(EVENTS),
      "/milk-transactions/tx-1": () =>
        json({ ...TX, state: "QUALITY_PENDING", unit_price: null, gross_amount: null, pricing_status: null }),
    });
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(await screen.findByText("Not priced")).toBeInTheDocument();
  });

  it("links to the supplier and the centre", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    await screen.findByText("Transaction created");
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links).toContain("/suppliers/s1");
    expect(links).toContain("/centers/c1");
  });

  it("keeps the page usable when the trail is unavailable", async () => {
    routeAll({ "/events": () => json({ detail: "down" }, 500) });
    await renderDetail(<TransactionDetailPage params={params()} />);
    // The pricing card still renders; only the timeline reports a failure.
    expect(await screen.findByText("= 450.00 KES")).toBeInTheDocument();
    expect(screen.getByText(/event trail is unavailable/i)).toBeInTheDocument();
  });

  it("explains a collection that cannot be loaded and offers the way back", async () => {
    routeAll({ "/milk-transactions/tx-1": () => json({ detail: "gone" }, 404) });
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
    expect(screen.getByRole("link", { name: /back to collections/i })).toBeInTheDocument();
  });
});
