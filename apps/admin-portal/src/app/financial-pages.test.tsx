/**
 * Settlement and payment operations (DEMO-006).
 *
 * These pages move money, so the tests defend the four things that stop them
 * lying about it:
 *
 *   1. filters are sent to the SERVER, and the KPI row comes from the
 *      platform's own aggregate — never from counting the visible page;
 *   2. no button is offered that the backend would reject — immutability is
 *      an absence of controls, not a disabled one;
 *   3. finalizing asks first, in words that say it cannot be undone; and
 *   4. the failure path is the platform's own transition, carrying the reason
 *      the operator typed — never a reason this portal invented.
 */
import { Suspense } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/settlements",
}));

import PaymentDetailPage from "@/app/payments/[id]/page";
import PaymentsPage from "@/app/payments/page";
import SettlementDetailPage from "@/app/settlements/[id]/page";
import SettlementsPage from "@/app/settlements/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const problem = (detail: string, status = 409) =>
  new Response(JSON.stringify({ title: "conflict", detail }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });

const settlement = (over: Record<string, unknown> = {}) => ({
  id: "st-1",
  settlement_number: "STL-2026-000004",
  supplier_id: "s1",
  center_id: "c1",
  period_from: "2026-08-01",
  period_to: "2026-08-10",
  currency: "KES",
  gross_amount: "3600.00",
  adjustments_amount: "0.00",
  net_amount: "3600.00",
  status: "calculated",
  line_count: 2,
  created_at: "2026-08-11T08:00:00+00:00",
  finalized_at: null,
  cancelled_at: null,
  ...over,
});

const LINES = [
  {
    id: "sl-1",
    calculation_id: "calc-1",
    transaction_id: "tx-1",
    transaction_date: "2026-08-09",
    quantity: "40.000",
    quantity_unit: "kg",
    unit_price: "45.0000",
    gross_amount: "1800.00",
    trace_reference: "RC-2026-MAIN v1",
  },
  {
    id: "sl-2",
    calculation_id: "calc-2",
    transaction_id: "tx-2",
    transaction_date: "2026-08-10",
    quantity: "40.000",
    quantity_unit: "kg",
    unit_price: "45.0000",
    gross_amount: "1800.00",
    trace_reference: "RC-2026-MAIN v1",
  },
];

const SETTLEMENT_REPORT = {
  by_status: [
    { status: "draft", count: 2, net_amount: "0.00" },
    { status: "calculated", count: 3, net_amount: "9000.00" },
    { status: "finalized", count: 7, net_amount: "42000.00" },
  ],
  finalized_net_total: "42000.00",
  total_settlements: 12,
  total_lines: 354,
};

const payment = (over: Record<string, unknown> = {}) => ({
  id: "pa-1",
  payment_number: "PAY-2026-000004",
  supplier_id: "s1",
  currency: "KES",
  method: "MOBILE_MONEY",
  amount: "3600.00",
  reference: "MPESA-DEMO",
  method_details: {},
  status: "processing",
  attempt_count: 1,
  failure_reason: null,
  note: null,
  line_count: 1,
  created_at: "2026-08-11T09:00:00+00:00",
  completed_at: null,
  failed_at: null,
  cancelled_at: null,
  ...over,
});

const PAYMENT_LINES = [
  { id: "pl-1", settlement_id: "st-1", settlement_number: "STL-2026-000004", amount: "3600.00" },
];

const PAYMENT_REPORT = {
  by_status: [{ status: "completed", count: 6, amount: "21600.00", currency: "KES" }],
  total_payments: 9,
  completed_count: 6,
  processing_count: 1,
  pending_count: 1,
  failed_count: 1,
  completed_amount: "21600.00",
  outstanding_amount: "18400.00",
  failed_amount: "3600.00",
  total_by_currency: { KES: "43600.00" },
};

const BALANCE = {
  settlement_id: "st-1",
  settlement_number: "STL-2026-000004",
  supplier_id: "s1",
  currency: "KES",
  payable: "3600.00",
  allocated: "3600.00",
  paid: "0.00",
  outstanding: "0.00",
  fully_paid: false,
};

const RECEIPT = {
  id: "rc-1",
  receipt_number: "RCP-2026-000004",
  payment_id: "pa-1",
  payment_number: "PAY-2026-000004",
  payment_reference: "MPESA-DEMO",
  payment_method: "MOBILE_MONEY",
  payment_date: "2026-08-11T09:05:00+00:00",
  supplier_id: "s1",
  supplier_name: "Amina Njoroge",
  supplier_code: "S-001",
  currency: "KES",
  gross_amount: "3600.00",
  adjustments_amount: "0.00",
  net_amount: "3600.00",
  status: "generated",
  render_format: "html",
  version: 1,
  line_count: 1,
  generated_at: "2026-08-11T09:05:30+00:00",
  delivered_at: null,
  archived_at: null,
};

const SUPPLIERS = {
  items: [
    {
      id: "s1",
      code: "S-001",
      status: "active",
      branch_id: null,
      full_name: "Amina Njoroge",
      phone: "+254700000001",
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

const CENTERS = {
  items: [
    {
      id: "c1",
      branch_id: "b1",
      name: "Kilima Hill",
      code: "KH-C1",
      status: "active",
      timezone: "Africa/Nairobi",
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

/**
 * `endsWith`-style matching where it matters: `/v1/settlements/st-1` and
 * `/v1/settlements/st-1/balance` differ only by suffix, and a careless
 * `includes` answers the wrong one — a bug DEMO-005 shipped once already.
 */
function routeAll(
  state: { settlement?: Record<string, unknown>; payment?: Record<string, unknown> } = {},
  overrides: Record<string, (url: string) => Response> = {},
) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler(url);
    }
    if (init?.method === "POST") return json(settlement(state.settlement));

    if (path.endsWith("/v1/reports/settlements")) return json(SETTLEMENT_REPORT);
    if (path.endsWith("/v1/reports/payments")) return json(PAYMENT_REPORT);
    if (path.endsWith("/v1/settlements/st-1/balance")) return json(BALANCE);
    if (path.endsWith("/v1/settlements/st-1"))
      return json({
        settlement: settlement(state.settlement),
        lines: LINES,
        totals_match_lines: true,
      });
    if (path.endsWith("/v1/settlements"))
      return json({ items: [settlement(state.settlement)], total: 1, limit: 15, offset: 0 });
    if (path.endsWith("/v1/payments/balances"))
      return json({ items: [BALANCE], total: 1, limit: 50, offset: 0 });
    if (path.endsWith("/v1/payments/pa-1"))
      return json({
        payment: payment(state.payment),
        lines: PAYMENT_LINES,
        attempts: [
          {
            id: "at-1",
            attempt_number: 1,
            provider: "mpesa-b2c",
            reference: "MPESA-DEMO",
            status: "processing",
            operator_id: "u1",
            failure_reason: null,
            started_at: "2026-08-11T09:01:00+00:00",
            completed_at: null,
          },
        ],
        totals_match_lines: true,
      });
    if (path.endsWith("/v1/payments"))
      return json({ items: [payment(state.payment)], total: 1, limit: 15, offset: 0 });
    if (path.endsWith("/v1/receipts")) return json({ items: [], total: 0, limit: 10, offset: 0 });
    if (path.endsWith("/v1/suppliers")) return json(SUPPLIERS);
    if (path.endsWith("/v1/collection-centers")) return json(CENTERS);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

/** Route params arrive through `use()`, which suspends. */
const renderDetail = async (ui: React.ReactElement) => {
  await act(async () => {
    render(<Suspense fallback={<span>loading route…</span>}>{ui}</Suspense>);
  });
};

const urls = (spy: ReturnType<typeof routeAll>) => spy.mock.calls.map((c) => String(c[0]));

describe("settlement list", () => {
  it("shows settlements with the platform's own figures", async () => {
    routeAll();
    render(<SettlementsPage />);
    expect(await screen.findByText("STL-2026-000004")).toBeInTheDocument();
    expect(screen.getByText("3,600.00")).toBeInTheDocument();
    // The KPI row is the reporting aggregate: 12 settlements, 354 lines,
    // 42,000.00 finalized — none of which appear in the single visible row.
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("354 collections settled")).toBeInTheDocument();
    expect(screen.getByText("42,000.00")).toBeInTheDocument();
  });

  it("sends every filter to the SERVER", async () => {
    const spy = routeAll();
    render(<SettlementsPage />);
    await screen.findByText("STL-2026-000004");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "finalized");
    await userEvent.selectOptions(screen.getByLabelText("Centre"), "c1");
    await userEvent.selectOptions(screen.getByLabelText("Supplier"), "s1");
    await userEvent.type(screen.getByLabelText("Search"), "STL-2026");

    await waitFor(() => {
      const last = urls(spy)
        .filter((u) => u.includes("/v1/settlements?"))
        .at(-1)!;
      expect(last).toContain("status=finalized");
      expect(last).toContain("center_id=c1");
      expect(last).toContain("supplier_id=s1");
      expect(last).toContain("q=STL-2026");
    });
  });
});

describe("settlement detail", () => {
  it("prints the stored totals and links every collection to its delivery", async () => {
    routeAll();
    await renderDetail(<SettlementDetailPage params={Promise.resolve({ id: "st-1" })} />);
    expect(await screen.findByText("STL-2026-000004")).toBeInTheDocument();
    // Gross and net are both 3,600.00 here — two separate stored strings, and
    // the page prints both rather than deriving one from the other.
    const summary = screen.getByText("Financial summary").closest("[data-slot=card]") as HTMLElement;
    expect(within(summary).getAllByText("3,600.00")).toHaveLength(2);
    expect(within(summary).getByText("0.00")).toBeInTheDocument();
    // Two lines of 1,800.00 — printed, never summed here.
    expect(screen.getAllByText("1,800.00")).toHaveLength(2);
    expect(screen.getByText(/Stored totals still match/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /tx-1/ })).toHaveAttribute(
      "href",
      "/transactions/tx-1",
    );
  });

  it("offers finalize only from calculated, and asks before doing it", async () => {
    routeAll();
    await renderDetail(<SettlementDetailPage params={Promise.resolve({ id: "st-1" })} />);
    await screen.findByText("STL-2026-000004");

    await userEvent.click(screen.getByRole("button", { name: "Finalize" }));
    // The warning must say what cannot be undone, not merely "are you sure".
    expect(
      screen.getByText(/is permanent\. Once finalized this settlement/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/cannot be edited, recalculated, or cancelled/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Yes, finalize permanently/ }),
    ).toBeInTheDocument();
  });

  it("offers NO lifecycle button once finalized — immutability, not a disabled control", async () => {
    routeAll({ settlement: { status: "finalized", finalized_at: "2026-08-11T10:00:00+00:00" } });
    await renderDetail(<SettlementDetailPage params={Promise.resolve({ id: "st-1" })} />);
    await screen.findByText("STL-2026-000004");

    for (const name of ["Finalize", "Calculate totals", "Collect period", "Cancel settlement"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.getByText(/BR-0010 makes it immutable/)).toBeInTheDocument();
    // A finalized settlement has a balance; the page shows the platform's.
    expect(await screen.findByText("Payment position")).toBeInTheDocument();
  });

  it("does not offer finalize on a draft, nor on a calculated settlement with no lines", async () => {
    routeAll({ settlement: { status: "draft" } });
    await renderDetail(<SettlementDetailPage params={Promise.resolve({ id: "st-1" })} />);
    await screen.findByText("STL-2026-000004");
    expect(screen.queryByRole("button", { name: "Finalize" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collect period" })).toBeInTheDocument();
  });

  it("shows the platform's refusal verbatim and re-reads afterwards", async () => {
    const spy = routeAll(
      {},
      {
        "/finalize": () => problem("settlement totals no longer match the lines — recalculate"),
      },
    );
    await renderDetail(<SettlementDetailPage params={Promise.resolve({ id: "st-1" })} />);
    await screen.findByText("STL-2026-000004");

    await userEvent.click(screen.getByRole("button", { name: "Finalize" }));
    await userEvent.click(screen.getByRole("button", { name: /Yes, finalize permanently/ }));

    expect(
      await screen.findByText(/settlement totals no longer match the lines/),
    ).toBeInTheDocument();
    // Re-read after the refusal: the platform is the authority on the state.
    const reads = urls(spy).filter((u) => u.endsWith("/v1/settlements/st-1"));
    expect(reads.length).toBeGreaterThan(1);
  });
});

describe("payment list", () => {
  it("uses the reporting aggregate for its KPIs and the platform's balances", async () => {
    routeAll();
    render(<PaymentsPage />);
    expect(await screen.findByText("PAY-2026-000004")).toBeInTheDocument();
    expect(screen.getByText("21,600.00")).toBeInTheDocument();
    expect(screen.getByText("18,400.00")).toBeInTheDocument();
    // The outstanding selector is the platform's, not a portal subtraction.
    expect(screen.getByText("Settlements awaiting payment")).toBeInTheDocument();
  });

  it("sends status, method and supplier to the SERVER", async () => {
    const spy = routeAll();
    render(<PaymentsPage />);
    await screen.findByText("PAY-2026-000004");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    await userEvent.selectOptions(screen.getByLabelText("Method"), "MOBILE_MONEY");

    await waitFor(() => {
      const last = urls(spy)
        .filter((u) => u.includes("/v1/payments?"))
        .at(-1)!;
      expect(last).toContain("status=failed");
      expect(last).toContain("method=MOBILE_MONEY");
    });
  });
});

describe("payment detail", () => {
  it("offers exactly the transitions the platform allows from processing", async () => {
    routeAll();
    await renderDetail(<PaymentDetailPage params={Promise.resolve({ id: "pa-1" })} />);
    await screen.findByText("PAY-2026-000004");

    expect(screen.getByRole("button", { name: "Record success" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record failure" })).toBeInTheDocument();
    // Cancelling a processing payment is deliberately impossible.
    expect(screen.queryByRole("button", { name: "Cancel payment" })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot be cancelled — money may already be in flight/)).toBeInTheDocument();
  });

  it("records a failure through the platform's own transition, with the typed reason", async () => {
    const spy = routeAll();
    await renderDetail(<PaymentDetailPage params={Promise.resolve({ id: "pa-1" })} />);
    await screen.findByText("PAY-2026-000004");

    await userEvent.click(screen.getByRole("button", { name: "Record failure" }));
    await userEvent.type(
      screen.getByLabelText("What went wrong?"),
      "provider rejected: invalid account",
    );
    await userEvent.click(screen.getByRole("button", { name: "Confirm failure" }));

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) => String(u).endsWith("/v1/payments/pa-1/fail"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call![1]!.body))).toEqual({
        reason: "provider rejected: invalid account",
      });
    });
  });

  it("shows the failure the platform recorded, and offers retry — not complete", async () => {
    routeAll({
      payment: {
        status: "failed",
        failure_reason: "provider rejected: invalid account",
        failed_at: "2026-08-11T09:10:00+00:00",
      },
    });
    await renderDetail(<PaymentDetailPage params={Promise.resolve({ id: "pa-1" })} />);
    await screen.findByText("PAY-2026-000004");

    expect(screen.getByText("provider rejected: invalid account")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel payment" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record success" })).not.toBeInTheDocument();
  });

  it("offers no operation at all once completed, and links the settlement it paid", async () => {
    routeAll({
      payment: { status: "completed", completed_at: "2026-08-11T09:05:00+00:00" },
    });
    await renderDetail(<PaymentDetailPage params={Promise.resolve({ id: "pa-1" })} />);
    await screen.findByText("PAY-2026-000004");

    for (const name of ["Record success", "Record failure", "Cancel payment", "Execute"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.getByText(/terminal and immutable/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "STL-2026-000004" })).toHaveAttribute(
      "href",
      "/settlements/st-1",
    );
  });

  it("offers the receipt for download when one exists", async () => {
    routeAll(
      { payment: { status: "completed", completed_at: "2026-08-11T09:05:00+00:00" } },
      { "/v1/receipts": () => json({ items: [RECEIPT], total: 1, limit: 10, offset: 0 }) },
    );
    await renderDetail(<PaymentDetailPage params={Promise.resolve({ id: "pa-1" })} />);
    await screen.findByText("PAY-2026-000004");

    expect(await screen.findByText("RCP-2026-000004")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download/ })).toHaveAttribute(
      "href",
      "/api/proxy/v1/receipts/rc-1/download?format=html",
    );
  });
});
