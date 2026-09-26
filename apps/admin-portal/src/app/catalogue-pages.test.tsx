/**
 * The catalogue, and things sold that are not the morning milk (WO-81).
 *
 * A milk shop's month sheet has a `Price` per household and an `other item`
 * rupee figure per household; the platform now has a product list, an item
 * recorded against a customer, and invoice lines that are a delivery OR an
 * item. These pin the portal's half:
 *
 *   * Admin → Products lists, adds, edits and deactivates — and says out
 *     loud that the default price is a suggestion;
 *   * the customer page has an Items section: record from the catalogue,
 *     price prefilled and editable, list, cancel;
 *   * a household with two standing orders is offered the product when
 *     recording a delivery, and the delivery carries it;
 *   * the deliveries page shows the period's items under the milk;
 *   * an invoice prints the line's kind and the product's NAME;
 *   * the CSV import's hint says plan_product must be a catalogue code.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/customers",
  useSearchParams: () => searchParams,
}));

import ProductsPage from "@/app/admin/products/page";
import CustomerDetailPage from "@/app/customers/[id]/page";
import DeliveriesPage from "@/app/deliveries/page";
import InvoiceDetailPage from "@/app/invoices/[id]/page";
import { CUSTOMER_IMPORT_SPEC } from "@/components/csv-import";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const SESSION = {
  authenticated: true,
  acting_tenant_id: null,
  user: { id: "u1", email: "owner@shop.example", full_name: "Shop Owner", status: "active" },
  tenant_id: "org-1",
  organization: {
    id: "org-1",
    name: "Mumbai Milk Shop",
    slug: "mumbai-milk",
    currency_code: "INR",
    timezone: "Asia/Kolkata",
    default_language: "en",
    supported_languages: ["en"],
  },
  membership: null,
  roles: [{ name: "tenant-admin", center_id: null }],
  center_scope: null,
  customer_id: null,
  permissions: ["*"],
};

const COW = {
  id: "pr-cow",
  code: "COW-MILK",
  name: "Cow milk",
  unit: "L",
  default_price: null,
  currency: "INR",
  active: true,
  sort_order: 0,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};
const DAHI = {
  ...COW,
  id: "pr-dahi",
  code: "DAHI-500G",
  name: "Dahi 500 g",
  unit: "pc",
  default_price: "40.00",
};
const OTHER = {
  ...COW,
  id: "pr-other",
  code: "OTHER",
  name: "Other shop item",
  unit: "pc",
  default_price: null,
  sort_order: 10000,
};

const CUSTOMER = {
  id: "cu-1",
  code: "CUS-2026-000005",
  name: "lodha casa foresta C-1603",
  customer_type: "household",
  phone: "+919800000005",
  alternate_phone: "",
  address: "C-1603, Lodha Casa Foresta",
  notes: "",
  status: "active",
  billing_mode: "credit",
  billing_day: 1,
  currency: "INR",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};
const plan = (id: string, product: string, quantity: string, price: string) => ({
  id,
  customer_id: "cu-1",
  product,
  default_quantity: quantity,
  quantity_unit: "L",
  unit_price: price,
  currency: "INR",
  effective_from: "2026-09-01",
  active: true,
  effective_to: null,
  weekdays: "1111111",
  slot: "morning",
  center_id: null,
  quantity_overrides: null,
  paused_from: null,
  paused_to: null,
  schedule_key: "schedule.daily",
  next_delivery: "2026-09-25",
});
const COW_PLAN = plan("pl-cow", "COW-MILK", "1.500", "74.0000");
const BUFFALO_PLAN = plan("pl-buf", "BUFFALO-MILK", "0.500", "56.0000");

const ITEM = {
  id: "it-1",
  customer_id: "cu-1",
  sale_date: "2026-09-10",
  product_code: "DAHI-500G",
  product_name: "Dahi 500 g",
  quantity: "2.000",
  unit: "pc",
  unit_price: "40.00",
  amount: "80.00",
  currency: "INR",
  status: "recorded",
  notes: "",
  recorded_by: "u1",
  recorded_via: "portal",
  invoice_id: null,
  created_at: "2026-09-10T08:00:00Z",
  cancelled_at: null,
  cancel_reason: "",
};

const INVOICE = {
  id: "in-1",
  customer_id: "cu-1",
  invoice_number: "INV-2026-000010",
  period_from: "2026-08-01",
  period_to: "2026-08-31",
  currency: "INR",
  subtotal: "1462.00",
  adjustments: "0.00",
  total: "1462.00",
  previous_balance: "244.00",
  amount_due: "1706.00",
  status: "issued",
  line_count: 2,
  issued_at: "2026-09-01T03:00:00Z",
  created_at: "2026-09-01T02:00:00Z",
};

function stub(overrides: Record<string, (url: string, init?: RequestInit) => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler(url, init);
    }
    if (path.endsWith("/api/auth/session")) return json(SESSION);
    if (path.endsWith("/v1/products") && init?.method === "POST")
      return json({ ...DAHI, id: "pr-new", code: "SHRIKHAND", name: "Shrikhand" }, 201);
    if (path.includes("/v1/products/") && init?.method === "PATCH")
      return json({ ...DAHI, active: false });
    if (path.endsWith("/v1/products")) return json({ items: [COW, DAHI, OTHER], total: 3 });
    if (path.endsWith("/v1/customers/cu-1/items") && init?.method === "POST")
      return json({ ...ITEM, id: "it-2" }, 201);
    if (path.endsWith("/v1/customers/cu-1/items"))
      return json({ items: [ITEM], total: 1, total_amount: "80.00", currency: "INR" });
    if (path.endsWith("/v1/items"))
      return json({ items: [ITEM], total: 1, total_amount: "80.00", currency: "INR" });
    if (path.includes("/v1/items/") && path.endsWith("/cancel"))
      return json({ ...ITEM, status: "cancelled", cancel_reason: "recorded in error" });
    if (path.endsWith("/v1/deliveries") && init?.method === "POST")
      return json(
        {
          id: "de-9",
          customer_id: "cu-1",
          delivery_date: "2026-09-25",
          slot: "morning",
          product: "BUFFALO-MILK",
          quantity: "0.500",
          quantity_unit: "L",
          unit_price: "56.0000",
          currency: "INR",
          amount: "28.00",
          status: "delivered",
          notes: "",
          invoice_id: null,
          plan_id: "pl-buf",
          created_at: "2026-09-25T02:00:00Z",
        },
        201,
      );
    if (path.endsWith("/v1/customers/cu-1"))
      return json({ customer: CUSTOMER, plans: [COW_PLAN, BUFFALO_PLAN] });
    if (path.endsWith("/v1/customers/cu-1/balance"))
      return json({
        customer_id: "cu-1",
        currency: "INR",
        invoiced: "0.00",
        paid: "0.00",
        outstanding: "0.00",
        unbilled_amount: "80.00",
        unbilled_deliveries: 0,
        unbilled_items: 1,
        open_invoices: 0,
      });
    if (path.endsWith("/v1/customers"))
      return json({ items: [CUSTOMER], total: 1, limit: 15, offset: 0 });
    if (path.endsWith("/v1/deliveries"))
      return json({
        items: [],
        total: 0,
        limit: 25,
        offset: 0,
        total_quantity: "0.000",
        total_amount: "0.00",
        currency: null,
      });
    if (path.endsWith("/v1/deliveries/report"))
      return json({
        date_from: "2026-09-19",
        date_to: "2026-09-25",
        deliveries: 0,
        delivered_quantity: "0.000",
        quantity_unit: "L",
        delivered_amount: "0.00",
        currency: null,
        customers_served: 0,
        by_status: [],
        by_route: [],
      });
    if (path.endsWith("/v1/invoices/in-1"))
      return json({
        invoice: INVOICE,
        lines: [
          {
            id: "il-1",
            line_kind: "delivery",
            delivery_id: "de-1",
            item_id: null,
            delivery_date: "2026-08-10",
            slot: "morning",
            product: "BUFFALO-MILK",
            product_name: "Buffalo milk",
            quantity: "0.750",
            quantity_unit: "L",
            unit_price: "56.0000",
            amount: "42.00",
          },
          {
            id: "il-2",
            line_kind: "item",
            delivery_id: null,
            item_id: "it-9",
            delivery_date: "2026-08-10",
            slot: "",
            product: "OTHER",
            product_name: "Other shop item",
            quantity: "1.000",
            quantity_unit: "pc",
            unit_price: "160.00",
            amount: "160.00",
          },
        ],
        paid: "0.00",
        outstanding: "1706.00",
        totals_match_lines: true,
      });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const urls = (spy: ReturnType<typeof stub>) => spy.mock.calls.map((c) => String(c[0]));
const bodies = (spy: ReturnType<typeof stub>, fragment: string) =>
  spy.mock.calls
    .filter((c) => String(c[0]).includes(fragment) && (c[1] as RequestInit)?.body)
    .map((c) => JSON.parse(String((c[1] as RequestInit).body)));

const renderRoute = async (ui: React.ReactElement) => {
  await act(async () => {
    render(<Suspense fallback={<span>loading route…</span>}>{ui}</Suspense>);
  });
};

beforeEach(() => {
  searchParams = new URLSearchParams();
  vi.unstubAllGlobals();
});
afterEach(() => vi.unstubAllGlobals());

describe("Admin → Products", () => {
  it("lists the catalogue and says the default price is only a suggestion", async () => {
    stub();
    await renderRoute(<ProductsPage />);
    expect(await screen.findByText("Dahi 500 g")).toBeInTheDocument();
    expect(screen.getByText("COW-MILK")).toBeInTheDocument();
    expect(screen.getByText("Other shop item")).toBeInTheDocument();
    // Two products without a price say so rather than showing 0.00.
    expect(screen.getAllByText("no price").length).toBe(2);
    expect(
      screen.getByText(/Milk sold by standing order is a product too and must be here/),
    ).toBeInTheDocument();
    expect(screen.getByText(/standing order always wins/)).toBeInTheDocument();
  });

  it("adds a product with a price as a STRING, and no code — the platform spells it (WO-107)", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<ProductsPage />);
    await screen.findByText("Dahi 500 g");
    await user.type(screen.getByLabelText("Name"), "Shrikhand");
    await user.type(screen.getByLabelText("Default price (optional)"), "60.00");
    await user.click(screen.getByRole("button", { name: "Add product" }));
    await waitFor(() => expect(bodies(spy, "/v1/products").length).toBe(1));
    // No `code` key at all: blank means "generate it from the name".
    expect(bodies(spy, "/v1/products")[0]).toEqual({
      name: "Shrikhand",
      unit: "pc",
      default_price: "60.00",
    });
    // The platform's spelling comes back in the confirmation.
    expect(await screen.findByRole("status")).toHaveTextContent("Added Shrikhand (SHRIKHAND)");
  });

  it("sends a code typed under More options, and a unit the shop sells by (WO-107)", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<ProductsPage />);
    await screen.findByText("Dahi 500 g");
    await user.type(screen.getByLabelText("Name"), "Paneer 200 g");
    await user.clear(screen.getByLabelText("Unit"));
    await user.type(screen.getByLabelText("Unit"), "packet");
    await user.type(screen.getByLabelText(/Code \(optional/), "PNR-200");
    await user.click(screen.getByRole("button", { name: "Add product" }));
    await waitFor(() => expect(bodies(spy, "/v1/products").length).toBe(1));
    expect(bodies(spy, "/v1/products")[0]).toEqual({
      code: "PNR-200",
      name: "Paneer 200 g",
      unit: "packet",
    });
  });

  it("deactivates rather than deletes, and says the bills keep it", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<ProductsPage />);
    await screen.findByText("Dahi 500 g");
    const row = screen.getByText("Dahi 500 g").closest("tr")!;
    await user.click(within(row).getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() =>
      expect(
        spy.mock.calls.some(
          (c) => String(c[0]).endsWith("/v1/products/pr-dahi") && (c[1] as RequestInit).method === "PATCH",
        ),
      ).toBe(true),
    );
    const body = bodies(spy, "/v1/products/pr-dahi")[0];
    expect(body.active).toBe(false);
    expect(await screen.findByRole("status")).toHaveTextContent(/stays on every bill/);
    // No DELETE anywhere on this page.
    expect(spy.mock.calls.some((c) => (c[1] as RequestInit)?.method === "DELETE")).toBe(false);
  });
});

describe("the customer page — items", () => {
  it("lists the items with their names, and the total", async () => {
    stub();
    await renderRoute(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    expect(await screen.findByText("Items")).toBeInTheDocument();
    const table = (await screen.findByText("Items sold to this customer")).closest("table")!;
    expect(within(table).getByText("Dahi 500 g")).toBeInTheDocument();
    expect(within(table).getByText("not yet billed")).toBeInTheDocument();
  });

  it("records an item with the catalogue's price prefilled and no price sent", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    await screen.findByText("Items");
    // The first product is the milk (no price); choose the dahi.
    await user.selectOptions(await screen.findByLabelText("Item"), "DAHI-500G");
    expect(screen.getByLabelText("Price each")).toHaveValue("40.00");
    await user.click(screen.getByRole("button", { name: "Record item" }));
    await waitFor(() => expect(bodies(spy, "/v1/customers/cu-1/items").length).toBe(1));
    const body = bodies(spy, "/v1/customers/cu-1/items")[0];
    expect(body).toEqual({ sale_date: expect.any(String), product_code: "DAHI-500G", quantity: "1" });
    expect(body).not.toHaveProperty("unit_price");
  });

  it("sends a typed price when the owner changes it", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    await screen.findByText("Items");
    await user.selectOptions(await screen.findByLabelText("Item"), "OTHER");
    const price = screen.getByLabelText("Price each");
    expect(price).toHaveValue("");
    await user.type(price, "160");
    await user.type(screen.getByLabelText("Note"), "sweets");
    await user.click(screen.getByRole("button", { name: "Record item" }));
    await waitFor(() => expect(bodies(spy, "/v1/customers/cu-1/items").length).toBe(1));
    expect(bodies(spy, "/v1/customers/cu-1/items")[0]).toMatchObject({
      product_code: "OTHER",
      unit_price: "160",
      notes: "sweets",
    });
  });

  it("cancels an item through the platform's own endpoint", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    const table = (await screen.findByText("Items sold to this customer")).closest("table")!;
    await user.click(within(table).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(urls(spy).some((u) => u.endsWith("/v1/items/it-1/cancel"))).toBe(true));
  });

  it("offers the product when the household has two standing orders, and sends it", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await renderRoute(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    const select = await screen.findByLabelText("Product");
    await user.selectOptions(select, "BUFFALO-MILK");
    // The quantity follows the chosen plan's standing figure.
    // The record form's own quantity box (the plan card has one too).
    expect(document.querySelector<HTMLInputElement>("#d-qty")).toHaveValue("0.500");
    await user.click(screen.getByRole("button", { name: "Record delivery" }));
    // WO-96 §4: asked first, then recorded.
    await user.click(await screen.findByRole("button", { name: "Yes, record it" }));
    await waitFor(() => expect(bodies(spy, "/v1/deliveries").length).toBe(1));
    expect(bodies(spy, "/v1/deliveries")[0]).toMatchObject({
      customer_id: "cu-1",
      product: "BUFFALO-MILK",
      quantity: "0.500",
    });
    expect(bodies(spy, "/v1/deliveries")[0]).not.toHaveProperty("unit_price");
  });
});

describe("the deliveries page — items under the milk", () => {
  it("shows the period's items with their kind, never as litres", async () => {
    const spy = stub();
    await renderRoute(<DeliveriesPage />);
    const table = (await screen.findByText("Items sold in this period", { selector: "caption" })).closest(
      "table",
    )!;
    expect(within(table).getByText("Dahi 500 g")).toBeInTheDocument();
    expect(within(table).getByText("item")).toBeInTheDocument();
    expect(within(table).getByText("2.000 pc")).toBeInTheDocument();
    expect(urls(spy).some((u) => u.includes("/v1/items?"))).toBe(true);
  });
});

describe("the invoice page — a line is a delivery or an item", () => {
  it("prints the kind and the product's NAME, not its code", async () => {
    stub();
    await renderRoute(<InvoiceDetailPage params={Promise.resolve({ id: "in-1" })} />);
    expect(await screen.findByText("Buffalo milk")).toBeInTheDocument();
    expect(screen.getByText("milk · morning")).toBeInTheDocument();
    expect(screen.getByText("Other shop item")).toBeInTheDocument();
    expect(screen.getByText("item")).toBeInTheDocument();
    expect(screen.queryByText("BUFFALO-MILK")).toBeNull();
  });
});

describe("the CSV import", () => {
  it("says plan_product must be a catalogue code", () => {
    expect(CUSTOMER_IMPORT_SPEC.hint).toMatch(/Admin → Products/);
    expect(CUSTOMER_IMPORT_SPEC.hint).toMatch(/refuses a code the catalogue does not know/);
  });
});
