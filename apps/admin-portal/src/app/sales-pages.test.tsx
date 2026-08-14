/**
 * The customer workflow in the portal (DEMO-009).
 *
 * The one rule these tests exist to defend: **the portal prints the
 * platform's money and never computes it.** A sales screen is the easiest
 * place in a dairy system to slip in a `quantity * rate` — it looks helpful,
 * it is instant, and it is a second pricing engine that will eventually
 * disagree with the first.
 *
 * So: the delivery form has no amount preview, the invoice page shows the
 * backend's own `totals_match_lines` verdict rather than summing the lines,
 * and the delivery list's totals are the ones the database returned for the
 * whole filtered set.
 */
import { Suspense } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** The URL the page is being deep-linked to; reset before each test. */
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/customers",
  useSearchParams: () => searchParams,
}));

import CustomerDetailPage from "@/app/customers/[id]/page";
import CustomersPage from "@/app/customers/page";
import DeliveriesPage from "@/app/deliveries/page";
import BillingPage from "@/app/billing/page";
import InvoiceDetailPage from "@/app/invoices/[id]/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const CUSTOMER = {
  id: "cu-1",
  code: "CUS-2026-000001",
  name: "Mama Njeri Household",
  customer_type: "household",
  phone: "+254701000101",
  alternate_phone: "",
  address: "12 Kilima Road",
  notes: "",
  status: "active",
  billing_mode: "credit",
  billing_day: 1,
  currency: "KES",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const PLAN = {
  id: "ps-1",
  customer_id: "cu-1",
  product: "RAW-COW-MILK",
  default_quantity: "2.000",
  quantity_unit: "L",
  unit_price: "62.0000",
  currency: "KES",
  effective_from: "2026-07-01",
  active: true,
};

const DELIVERY = {
  id: "de-1",
  customer_id: "cu-1",
  delivery_date: "2026-08-11",
  slot: "morning",
  product: "RAW-COW-MILK",
  quantity: "2.000",
  quantity_unit: "L",
  unit_price: "62.0000",
  currency: "KES",
  amount: "124.00",
  status: "delivered",
  notes: "",
  invoice_id: null,
  plan_id: "ps-1",
  created_at: "2026-08-11T06:00:00Z",
};

const SKIPPED = {
  ...DELIVERY,
  id: "de-2",
  delivery_date: "2026-08-10",
  status: "skipped",
  amount: "0.00",
};

const INVOICE = {
  id: "in-1",
  customer_id: "cu-1",
  invoice_number: "INV-2026-000001",
  period_from: "2026-07-13",
  period_to: "2026-08-11",
  currency: "KES",
  subtotal: "3658.00",
  adjustments: "0.00",
  total: "3658.00",
  previous_balance: "0.00",
  amount_due: "3658.00",
  status: "issued",
  line_count: 28,
  issued_at: "2026-08-12T09:00:00Z",
  created_at: "2026-08-12T08:00:00Z",
};

const REPORT = {
  date_from: "2026-08-05",
  date_to: "2026-08-12",
  currency: "KES",
  quantity_unit: "L",
  deliveries: 36,
  customers_served: 6,
  total_quantity: "180.500",
  total_amount: "10234.50",
  skipped: 3,
  by_customer: [
    {
      customer_id: "cu-1",
      code: "CUST-0001",
      name: "Mama Njeri Household",
      product: "RAW-COW-MILK",
      deliveries: 24,
      quantity: "120.000",
      unit_price: "56.0000",
      amount: "6720.00",
      skipped: 1,
    },
    {
      customer_id: "cu-2",
      code: "CUST-0002",
      name: "Adiga Tiffin Room",
      product: "RAW-COW-MILK",
      deliveries: 12,
      quantity: "60.500",
      // The rate changed inside the window: the platform sends null rather
      // than blending two rates into one.
      unit_price: null,
      amount: "3514.50",
      skipped: 2,
    },
  ],
  by_day: [
    {
      delivery_date: "2026-08-11",
      deliveries: 6,
      customers: 6,
      quantity: "30.000",
      amount: "1705.75",
    },
    {
      delivery_date: "2026-08-12",
      deliveries: 6,
      customers: 6,
      quantity: "30.000",
      amount: "1705.75",
    },
  ],
};

const STATEMENT = {
  customer_id: "cu-1",
  code: "CUS-2026-000001",
  name: "Mama Njeri Household",
  currency: "KES",
  date_from: "2026-08-01",
  date_to: "2026-08-12",
  opening_balance: "500.00",
  billed: "3658.00",
  paid: "3658.00",
  closing_balance: "500.00",
  entries: [
    {
      entry_date: "2026-08-12",
      kind: "invoice",
      reference: "INV-2026-000001",
      detail: "2026-07-01 — 2026-07-31",
      debit: "3658.00",
      credit: "0.00",
      balance: "4158.00",
    },
    {
      entry_date: "2026-08-12",
      kind: "payment",
      reference: "CPY-2026-000001",
      detail: "MOBILE_MONEY",
      debit: "0.00",
      credit: "3658.00",
      balance: "500.00",
    },
  ],
};

function routeAll(overrides: Record<string, (url: string) => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler(url);
    }
    if (init?.method === "POST") return json(DELIVERY, 201);
    if (path.endsWith("/v1/customers/cu-1/balance"))
      return json({
        customer_id: "cu-1",
        currency: "KES",
        invoiced: "3658.00",
        paid: "3658.00",
        outstanding: "0.00",
        unbilled_amount: "248.00",
        unbilled_deliveries: 2,
        open_invoices: 0,
      });
    if (path.endsWith("/v1/customers/cu-1/statement")) return json(STATEMENT);
    if (path.endsWith("/v1/customers/cu-1"))
      return json({ customer: CUSTOMER, plans: [PLAN] });
    if (path.endsWith("/v1/customers"))
      return json({ items: [CUSTOMER], total: 1, limit: 15, offset: 0 });
    if (path.endsWith("/v1/deliveries/report")) return json(REPORT);
    if (path.endsWith("/v1/deliveries"))
      return json({
        items: [DELIVERY, SKIPPED],
        total: 36,
        limit: 25,
        offset: 0,
        total_quantity: "180.500",
        total_amount: "10234.50",
      });
    if (path.endsWith("/v1/invoices/in-1"))
      return json({
        invoice: INVOICE,
        lines: [
          {
            id: "il-1",
            delivery_id: "de-1",
            delivery_date: "2026-08-11",
            slot: "morning",
            product: "RAW-COW-MILK",
            quantity: "2.000",
            quantity_unit: "L",
            unit_price: "62.0000",
            amount: "124.00",
          },
        ],
        paid: "3658.00",
        outstanding: "0.00",
        totals_match_lines: true,
      });
    if (path.endsWith("/v1/invoices"))
      return json({ items: [INVOICE], total: 1, limit: 12, offset: 0 });
    if (path.endsWith("/v1/customer-payments"))
      return json({
        items: [
          {
            id: "pa-1",
            customer_id: "cu-1",
            payment_number: "CPY-2026-000001",
            amount: "3658.00",
            currency: "KES",
            method: "MOBILE_MONEY",
            reference: "MPESA-1",
            status: "recorded",
            notes: "",
            received_at: "2026-08-12T10:00:00Z",
            created_at: "2026-08-12T10:00:00Z",
          },
        ],
        total: 1,
        limit: 12,
        offset: 0,
      });
    if (path.endsWith("/v1/customer-receipts"))
      return json({
        items: [
          {
            id: "rc-1",
            receipt_number: "CRC-2026-000001",
            payment_id: "pa-1",
            payment_number: "CPY-2026-000001",
            customer_id: "cu-1",
            customer_name: "Mama Njeri Household",
            customer_code: "CUS-2026-000001",
            amount: "3658.00",
            currency: "KES",
            method: "MOBILE_MONEY",
            reference: "MPESA-1",
            applied_to: "INV-2026-000001",
            generated_at: "2026-08-12T10:00:05Z",
          },
        ],
        total: 1,
        limit: 12,
        offset: 0,
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

describe("customers", () => {
  it("lists customers with their codes", async () => {
    routeAll();
    render(<CustomersPage />);
    expect(await screen.findByText("Mama Njeri Household")).toBeInTheDocument();
    expect(screen.getByText("CUS-2026-000001")).toBeInTheDocument();
  });

  it("sends every filter to the SERVER", async () => {
    const spy = routeAll();
    render(<CustomersPage />);
    await screen.findByText("Mama Njeri Household");

    await userEvent.type(screen.getByLabelText("Search"), "njeri");
    await userEvent.selectOptions(screen.getByLabelText("Type"), "household");

    await waitFor(() => {
      const last = urls(spy)
        .filter((u) => u.includes("/v1/customers?"))
        .at(-1)!;
      expect(last).toContain("q=njeri");
      expect(last).toContain("customer_type=household");
    });
  });
});

describe("customer detail — the whole workflow", () => {
  const params = () => Promise.resolve({ id: "cu-1" });

  it("shows the account, the plan and the platform's own figures", async () => {
    routeAll();
    await renderDetail(<CustomerDetailPage params={params()} />);

    expect(await screen.findByText("Mama Njeri Household")).toBeInTheDocument();
    // Outstanding, invoiced, paid and the bill still forming — all the
    // backend's numbers.
    expect(screen.getAllByText("3,658.00").length).toBeGreaterThan(0);
    expect(screen.getByText("248.00")).toBeInTheDocument();
    expect(
      screen.getByText(/2 delivered, awaiting a bill/),
    ).toBeInTheDocument();
  });

  it("records a delivery WITHOUT sending a price", async () => {
    const spy = routeAll();
    await renderDetail(<CustomerDetailPage params={params()} />);
    await screen.findByText("Record a delivery");

    await userEvent.click(
      screen.getByRole("button", { name: "Record delivery" }),
    );

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) =>
        String(u).endsWith("/v1/deliveries"),
      );
      expect(call).toBeDefined();
      const body = JSON.parse(String(call![1]!.body));
      expect(body.customer_id).toBe("cu-1");
      expect(body.quantity).toBe("2.000");
      // The rate and the amount are the platform's. A client that could send
      // them could sell milk at any price it liked.
      expect(body).not.toHaveProperty("unit_price");
      expect(body).not.toHaveProperty("amount");
    });
  });

  it("shows no computed amount preview beside the quantity", async () => {
    routeAll();
    await renderDetail(<CustomerDetailPage params={params()} />);
    await screen.findByText("Record a delivery");
    // 2.000 × 62.0000 would be 124.00. It must not appear until the platform
    // has said so — and the only 124.00 on the page is the delivery already
    // recorded, in the history table.
    expect(screen.getAllByText("124.00")).toHaveLength(1);
  });

  it("prints the delivery history and the platform's totals", async () => {
    routeAll();
    await renderDetail(<CustomerDetailPage params={params()} />);
    await screen.findByText("Delivery history");
    expect(screen.getByText("10,234.50")).toBeInTheDocument();
    expect(screen.getByText("180.500")).toBeInTheDocument();
    // A skipped delivery is worth nothing, and says so. (The outstanding
    // tile is also 0.00, hence the count rather than a single match.)
    expect(screen.getAllByText("0.00").length).toBeGreaterThanOrEqual(2);
  });

  it("links the bill, and shows the receipt the platform generated", async () => {
    routeAll();
    await renderDetail(<CustomerDetailPage params={params()} />);
    expect(
      await screen.findByRole("link", { name: "INV-2026-000001" }),
    ).toHaveAttribute("href", "/invoices/in-1");
    expect(screen.getByText("CRC-2026-000001")).toBeInTheDocument();
    // Twice since DEMO-015: in the payments list and again on the statement.
    expect(screen.getAllByText("CPY-2026-000001").length).toBeGreaterThan(0);
  });

  it("records a payment through the platform", async () => {
    const spy = routeAll();
    await renderDetail(<CustomerDetailPage params={params()} />);
    await screen.findByText("Payments received");

    await userEvent.type(screen.getByLabelText("Amount (KES)"), "500.00");
    await userEvent.click(
      screen.getByRole("button", { name: "Record payment" }),
    );

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) =>
        String(u).endsWith("/v1/customer-payments"),
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call![1]!.body))).toMatchObject({
        customer_id: "cu-1",
        amount: "500.00",
        method: "CASH",
      });
    });
  });
});

describe("deliveries and the daily report", () => {
  it("shows the report aggregated by the platform, day by day", async () => {
    routeAll();
    render(<DeliveriesPage />);
    expect(await screen.findByText("Day by day")).toBeInTheDocument();
    expect(screen.getAllByText("36").length).toBeGreaterThan(0);
    // Customers served — the figure appears in the KPI tile and in each
    // day's row, so count rather than assume one.
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("10,234.50").length).toBeGreaterThan(0);
  });

  it("states that the totals cover the whole filtered set, not the page", async () => {
    routeAll();
    render(<DeliveriesPage />);
    expect(
      await screen.findByText(/Across all 36 matching deliveries/),
    ).toBeInTheDocument();
  });

  it("sends the date window and the customer filter to the SERVER", async () => {
    const spy = routeAll();
    render(<DeliveriesPage />);
    await screen.findByText("Day by day");

    await waitFor(() => {
      const last = urls(spy)
        .filter((u) => u.includes("/v1/deliveries?"))
        .at(-1)!;
      expect(last).toContain("date_from=");
      expect(last).toContain("date_to=");
    });
    const reportCall = urls(spy).find((u) =>
      u.includes("/v1/deliveries/report"),
    );
    expect(reportCall).toContain("date_from=");
  });
});

describe("the monthly bill", () => {
  const params = () => Promise.resolve({ id: "in-1" });

  it("shows the statement and the platform's reconciliation verdict", async () => {
    routeAll();
    await renderDetail(<InvoiceDetailPage params={params()} />);

    // The number appears in the heading and in the breadcrumb.
    expect(
      (await screen.findAllByText("INV-2026-000001")).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("3,658.00").length).toBeGreaterThan(0);
    // The backend's own answer, not a sum computed here.
    expect(
      screen.getByText(/still equals the 28 lines below/),
    ).toBeInTheDocument();
    expect(screen.getByText(/verified by the platform/)).toBeInTheDocument();
  });

  it("SHOWS a reconciliation failure rather than hiding it", async () => {
    routeAll({
      "/v1/invoices/in-1": () =>
        json({
          invoice: INVOICE,
          lines: [],
          paid: "0.00",
          outstanding: "3658.00",
          totals_match_lines: false,
        }),
    });
    await renderDetail(<InvoiceDetailPage params={params()} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/no longer matches the lines/);
  });

  it("offers no lifecycle control once the bill is issued", async () => {
    routeAll();
    await renderDetail(<InvoiceDetailPage params={params()} />);
    await screen.findAllByText("INV-2026-000001");
    expect(
      screen.queryByRole("button", { name: "Issue bill" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel bill" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/immutable/)).toBeInTheDocument();
  });

  it("asks before issuing a draft, naming what cannot be undone", async () => {
    routeAll({
      "/v1/invoices/in-1": () =>
        json({
          invoice: { ...INVOICE, status: "draft", issued_at: null },
          lines: [],
          paid: "0.00",
          outstanding: "3658.00",
          totals_match_lines: true,
        }),
    });
    await renderDetail(<InvoiceDetailPage params={params()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Issue bill" }),
    );
    expect(screen.getByText(/is permanent/)).toBeInTheDocument();
    expect(
      screen.getByText(/cannot be edited or cancelled/),
    ).toBeInTheDocument();
  });
});

// --- deep links (DEMO-010) ---------------------------------------------------
//
// The dashboard's "needs attention" list promises a filtered destination:
// "22 deliveries made but not yet billed → review". If the page ignores the
// query string it shows everything, which in front of a customer reads as a
// filter that does not work. These assert the promise is kept — and, just as
// importantly, that the narrowing happens in the DATABASE rather than by
// fetching everything and hiding rows.

describe("deep links from the dashboard", () => {
  beforeEach(() => {
    searchParams = new URLSearchParams();
  });

  it("lands on deliveries that are not yet billed, and asks the server for them", async () => {
    searchParams = new URLSearchParams("invoiced=false");
    const spy = routeAll();
    render(<DeliveriesPage />);

    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter(
          (u) => u.includes("/v1/deliveries?") && u.includes("invoiced=false"),
        );
      expect(asked.length).toBeGreaterThan(0);
    });
    expect(await screen.findByLabelText("Billed")).toHaveValue("false");
  });

  it("lands on drafted bills, and asks the server for them", async () => {
    searchParams = new URLSearchParams("status=draft");
    const spy = routeAll();
    render(<BillingPage />);

    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter(
          (u) => u.includes("/v1/invoices?") && u.includes("status=draft"),
        );
      expect(asked.length).toBeGreaterThan(0);
    });
    expect(await screen.findByLabelText("Status")).toHaveValue("draft");
  });

  it("shows every delivery when the URL asks for nothing in particular", async () => {
    const spy = routeAll();
    render(<DeliveriesPage />);

    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/v1/deliveries?"));
      expect(asked.length).toBeGreaterThan(0);
      expect(asked.every((u) => !u.includes("invoiced="))).toBe(true);
    });
  });
});

describe("the customer statement (DEMO-015)", () => {
  it("prints the platform's running balance rather than recomputing it", async () => {
    routeAll();
    await renderDetail(
      <CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />,
    );

    // Twice: the card title and the table's screen-reader caption.
    expect((await screen.findAllByText("Statement")).length).toBeGreaterThan(0);
    // Opening and closing are the platform's, and they are NOT the same
    // number — a screen that summed the two entries itself would show 0.00.
    expect(screen.getAllByText("500.00").length).toBeGreaterThan(0);
    // Both appear twice on this page: once in their own list, once here.
    expect(screen.getAllByText("INV-2026-000001").length).toBeGreaterThan(0);
    expect(screen.getAllByText("CPY-2026-000001").length).toBeGreaterThan(0);
    // The running balance after the bill, straight from the response.
    expect(screen.getByText("4,158.00")).toBeInTheDocument();
  });

  it("asks the platform for the window rather than computing a month", async () => {
    const spy = routeAll();
    await renderDetail(
      <CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />,
    );
    await waitFor(() =>
      expect(
        urls(spy).some((u) => u.includes("/v1/customers/cu-1/statement")),
      ).toBe(true),
    );
    // No date_from/date_to: the dairy's own month is the server's to decide.
    const call = urls(spy).find((u) => u.includes("/statement"))!;
    expect(call).not.toContain("date_from");
  });

  it("survives an API that has never heard of a statement", async () => {
    // A rolling deploy can leave the portal ahead of the API for seconds.
    // The rest of the page must still render.
    routeAll({ "/statement": () => json({ title: "not_found" }, 404) });
    await renderDetail(
      <CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />,
    );
    expect(await screen.findByText("Mama Njeri Household")).toBeInTheDocument();
    expect(screen.queryAllByText("Statement")).toHaveLength(0);
  });
});

describe("the delivery report as a file (DEMO-015)", () => {
  it("offers a download that carries the same window as the screen", async () => {
    routeAll();
    render(<DeliveriesPage />);
    const link = await screen.findByRole("link", { name: /download csv/i });
    const href = link.getAttribute("href") ?? "";
    expect(href).toContain("/v1/deliveries/report.csv");
    expect(href).toContain("date_from=");
    expect(href).toContain("date_to=");
  });

  it("takes every label from the catalog, including the ones it once hard-coded", () => {
    // Not a rendering assertion — a source one. The failure mode this guards
    // is a string that LOOKS translated because the catalog has the key,
    // while the page renders a literal beside it (DEMO-015, found in a
    // browser with the page half in Hindi).
    const source = readFileSync(
      resolve(process.cwd(), "src/app/deliveries/page.tsx"),
      "utf8",
    );
    for (const literal of [
      'title="Deliveries"',
      'label="Quantity"',
      'label="Value"',
      'label="Customers served"',
      'aria-label="Delivery summary"',
    ]) {
      expect(source).not.toContain(literal);
    }
  });

  it("shows who the milk went to, with the platform's own rate", async () => {
    routeAll();
    render(<DeliveriesPage />);
    expect((await screen.findAllByText("By customer")).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("Adiga Tiffin Room")).toBeInTheDocument();
    expect(screen.getByText("6,720.00")).toBeInTheDocument();
    // A customer whose rate changed inside the window: the platform sent null
    // rather than an average, and the screen says so instead of inventing one.
    expect(screen.getByText("Mixed")).toBeInTheDocument();
  });
});
