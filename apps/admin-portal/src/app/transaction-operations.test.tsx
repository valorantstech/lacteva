/**
 * Transactions — operational list and detail (DEMO-007).
 *
 * The four things this screen could most easily lie about, defended:
 *
 *   1. the financial columns cost ONE call per page, not one per row;
 *   2. a collection with no settlement is drawn as an absence, never as a
 *      settled row with a zero in it;
 *   3. the capture SOURCE of every reading is shown, so a hand-entered weight
 *      cannot be mistaken for an instrument's; and
 *   4. the money trail COMPARES the platform's figures and never computes
 *      them — a mismatch is displayed, not smoothed over.
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
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** 10.000 kg at 45.0000 = 450.00 KES, entered by an operator. */
const TX = {
  id: "tx-1",
  session_id: "se-1",
  center_id: "c1",
  supplier_id: "s1",
  operator_id: "u1",
  state: "COMPLETED",
  milk_type: "cow",
  milk_type_custom: null,
  container_type: "can",
  container_identifier: "CAN-01",
  arrival_temperature_c: null,
  arrived_at: null,
  weight_unit: "kg",
  gross_weight: 12,
  tare_weight: 2,
  net_weight: 10,
  weight_source: "manual",
  fat: 4.2,
  snf: 8.6,
  clr: 28.5,
  density: null,
  quality_temperature_c: null,
  quality_remarks: "",
  quality_source: "manual",
  pricing_status: "priced",
  unit_price: "45.0000",
  gross_amount: "450.00",
  currency: "KES",
  calculation_id: "calc-1",
  pricing_detail: "RC-2026-MAIN v1 band [4.0, 5.0)",
  rejected_reason: null,
  decided_by: "u1",
  decided_at: "2026-08-10T07:44:00+00:00",
  cancelled_reason: null,
  created_at: "2026-08-10T07:30:00+00:00",
  completed_at: "2026-08-10T07:45:00+00:00",
};

const SECOND = { ...TX, id: "tx-2", created_at: "2026-08-10T08:30:00+00:00" };

const STATUS = {
  items: [
    {
      transaction_id: "tx-1",
      last_event_type: "TransactionCompleted",
      last_event_at: "2026-08-10T07:45:00+00:00",
      settlement_id: "st-1",
      settlement_number: "STL-2026-000004",
      settlement_status: "finalized",
      settled_amount: "450.00",
      payment_id: "pa-1",
      payment_number: "PAY-2026-000004",
      payment_status: "completed",
      receipt_id: "rc-1",
      receipt_number: "RCP-2026-000004",
      receipt_status: "generated",
    },
    {
      // Deliberately bare: this row has been collected and nothing more.
      transaction_id: "tx-2",
      last_event_type: "TransactionCompleted",
      last_event_at: "2026-08-10T08:45:00+00:00",
      settlement_id: null,
      settlement_number: null,
      settlement_status: null,
      settled_amount: null,
      payment_id: null,
      payment_number: null,
      payment_status: null,
      receipt_id: null,
      receipt_number: null,
      receipt_status: null,
    },
  ],
};

const EVENTS = [
  {
    sequence: 1,
    event_type: "TransactionCreated",
    data: {},
    actor_id: "u1",
    created_at: "2026-08-10T07:30:00+00:00",
  },
  {
    sequence: 2,
    event_type: "WeightCaptured",
    data: { gross: 12, tare: 2, net: 10 },
    actor_id: "u1",
    created_at: "2026-08-10T07:33:00+00:00",
  },
  {
    sequence: 3,
    event_type: "TransactionCompleted",
    data: {},
    actor_id: null,
    created_at: "2026-08-10T07:45:00+00:00",
  },
];

const CHAIN = {
  transaction_id: "tx-1",
  settlement: {
    id: "st-1",
    settlement_number: "STL-2026-000004",
    status: "finalized",
    period_from: "2026-08-01",
    period_to: "2026-08-10",
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

const CENTER = {
  id: "c1",
  branch_id: "b1",
  name: "Kilima Hill",
  code: "KH-C1",
  status: "active",
  timezone: "Africa/Nairobi",
};

const SUPPLIER = {
  id: "s1",
  code: "S-001",
  status: "active",
  branch_id: null,
  full_name: "Amina Njoroge",
  phone: "+254700000001",
};

function routeAll(overrides: Record<string, (url: string) => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const path = url.split("?")[0];
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler(url);
    }
    if (path.endsWith("/v1/reports/collection/operational-status"))
      return json(STATUS);
    if (path.endsWith("/v1/reports/collection/daily")) return json(DAILY);
    if (path.endsWith("/chain")) return json(CHAIN);
    if (path.endsWith("/v1/milk-transactions/tx-1/events")) return json(EVENTS);
    if (path.endsWith("/v1/milk-transactions/tx-1")) return json(TX);
    if (path.endsWith("/v1/milk-transactions"))
      return json({ items: [TX, SECOND], total: 2, limit: 15, offset: 0 });
    if (path.endsWith("/v1/collection-centers/c1"))
      return json({
        center: CENTER,
        settings: {},
        operating_windows: [],
        calendar: [],
      });
    if (path.endsWith("/v1/collection-centers"))
      return json({ items: [CENTER], total: 1, limit: 100, offset: 0 });
    if (path.endsWith("/v1/suppliers/s1"))
      return json({
        supplier: SUPPLIER,
        profile: {
          full_name: "Amina Njoroge",
          phone: "",
          village: "",
          national_id: "",
        },
        center_ids: ["c1"],
        bank_accounts: [],
        documents: [],
      });
    if (path.endsWith("/v1/suppliers"))
      return json({ items: [SUPPLIER], total: 1, limit: 100, offset: 0 });
    if (path.endsWith("/v1/members"))
      return json([
        { user_id: "u1", status: "active", joined_at: "2026-01-01T00:00:00Z" },
      ]);
    if (path.includes("/v1/identity/users/"))
      return json({
        id: "u1",
        email: "wanjiku@lacteva.example",
        full_name: "Wanjiku Mbugua",
        locale: "en",
        is_active: true,
      });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

const renderDetail = async (ui: React.ReactElement) => {
  await act(async () => {
    render(<Suspense fallback={<span>loading route…</span>}>{ui}</Suspense>);
  });
};

const urls = (spy: ReturnType<typeof routeAll>) =>
  spy.mock.calls.map((c) => String(c[0]));

describe("transactions list", () => {
  it("asks for the whole page's financial position in ONE call", async () => {
    const spy = routeAll();
    render(<TransactionsPage />);
    await screen.findByText("STL-2026-000004");

    const statusCalls = urls(spy).filter((u) =>
      u.includes("operational-status"),
    );
    expect(statusCalls).toHaveLength(1);
    // Both ids in the one request — never a call per row.
    expect(statusCalls[0]).toContain("transaction_ids=tx-1");
    expect(statusCalls[0]).toContain("transaction_ids=tx-2");
    // And the per-row chain endpoint is not used here at all.
    expect(urls(spy).some((u) => u.includes("/chain"))).toBe(false);
  });

  it("shows settlement and payment where they exist, and an absence where they do not", async () => {
    routeAll();
    render(<TransactionsPage />);

    expect(
      await screen.findByRole("link", { name: "STL-2026-000004" }),
    ).toHaveAttribute("href", "/settlements/st-1");
    expect(
      screen.getByRole("link", { name: "PAY-2026-000004" }),
    ).toHaveAttribute("href", "/payments/pa-1");
    // The second collection is drawn as an absence, not as a zero.
    expect(screen.getByText("not settled")).toBeInTheDocument();
    expect(screen.getByText("not paid")).toBeInTheDocument();
  });

  it("shows the last activity from the platform's own event log", async () => {
    routeAll();
    render(<TransactionsPage />);
    expect(
      (await screen.findAllByText("Transaction completed")).length,
    ).toBeGreaterThan(0);
  });

  it("sends every filter to the SERVER", async () => {
    const spy = routeAll();
    render(<TransactionsPage />);
    await screen.findByText("STL-2026-000004");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "COMPLETED");
    await userEvent.selectOptions(screen.getByLabelText("Centre"), "c1");
    await userEvent.selectOptions(screen.getByLabelText("Supplier"), "s1");

    await waitFor(() => {
      const last = urls(spy)
        .filter((u) => u.includes("/v1/milk-transactions?"))
        .at(-1)!;
      expect(last).toContain("state=COMPLETED");
      expect(last).toContain("center_id=c1");
      expect(last).toContain("supplier_id=s1");
      expect(last).toContain("date_from=");
    });
  });

  it("offers no settlement or payment filter, because the platform cannot apply one", async () => {
    routeAll();
    render(<TransactionsPage />);
    await screen.findByText("STL-2026-000004");
    // A control that silently searched only the visible page would be worse
    // than no control at all.
    expect(screen.queryByLabelText("Settlement")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Payment")).not.toBeInTheDocument();
  });

  it("survives the financial call failing, and still shows the milk", async () => {
    routeAll({ "operational-status": () => json({ title: "boom" }, 500) });
    render(<TransactionsPage />);
    // The collection is still listed; only the money columns are empty.
    expect(await screen.findAllByText("2026-08-10")).toHaveLength(2);
    expect(screen.getAllByText("not settled")).toHaveLength(2);
  });
});

describe("transaction detail", () => {
  const params = () => Promise.resolve({ id: "tx-1" });

  it("names the centre and the supplier instead of showing identifiers", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(
      await screen.findByRole("link", { name: /Kilima Hill/ }),
    ).toHaveAttribute("href", "/centers/c1");
    expect(screen.getByRole("link", { name: /Amina Njoroge/ })).toHaveAttribute(
      "href",
      "/suppliers/s1",
    );
  });

  it("says how the weight and the quality were obtained", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    await screen.findByText("Weight source");
    // "manual" is the domain's own word, and it is labelled rather than hidden.
    expect(screen.getAllByText("manual").length).toBe(2);
    expect(screen.getAllByText("entered by an operator").length).toBe(2);
  });

  it("follows the money and states that the two figures agree", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(await screen.findByText("Money trail")).toBeInTheDocument();
    expect(
      screen.getByText(
        /recorded this collection at exactly its collection value/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/difference 0\.00 KES/)).toBeInTheDocument();
  });

  it("SHOWS a disagreement rather than hiding it", async () => {
    routeAll({
      "/chain": () =>
        json({
          ...CHAIN,
          settlement: { ...CHAIN.settlement, line_amount: "449.00" },
        }),
    });
    await renderDetail(<TransactionDetailPage params={params()} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      /449\.00 KES for a collection worth 450\.00 KES/,
    );
    expect(alert).toHaveTextContent(/should be identical/);
  });

  it("treats 450.0 and 450.00 as the same amount", async () => {
    // DEMO-002 shipped a reconciliation that called these a mismatch. They are
    // the same money written two ways.
    routeAll({
      "/chain": () =>
        json({
          ...CHAIN,
          settlement: { ...CHAIN.settlement, line_amount: "450.0" },
        }),
    });
    await renderDetail(<TransactionDetailPage params={params()} />);
    expect(
      await screen.findByText(
        /recorded this collection at exactly its collection value/,
      ),
    ).toBeInTheDocument();
  });

  it("attributes each event to whoever the platform recorded", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    await screen.findByText("Transaction created");
    // The operator's real name, resolved once from the staff roster...
    expect(screen.getAllByText(/Wanjiku Mbugua/).length).toBeGreaterThan(0);
    // ...and an unattributed event says so rather than guessing.
    expect(screen.getAllByText(/the platform/).length).toBeGreaterThan(0);
    // The recorded payload is summarised from the stored keys only.
    expect(screen.getByText(/net 10/)).toBeInTheDocument();
  });

  it("links the settlement, the payment and the receipt to their own pages", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);
    await screen.findByText("Money trail");
    const settlementLinks = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("href") === "/settlements/st-1");
    const paymentLinks = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("href") === "/payments/pa-1");
    expect(settlementLinks.length).toBeGreaterThan(0);
    expect(paymentLinks.length).toBeGreaterThan(0);
  });
});
