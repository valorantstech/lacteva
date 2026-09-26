/**
 * The portal on a phone (WO-96).
 *
 * The shop owner has no laptop. The architect's 360px audit found one pattern
 * everywhere money is: tables list names first and money and buttons last,
 * so the amounts and the actions are exactly what a phone pushes off the
 * right edge. These tests choose the phone (`matchMedia` says the narrow
 * query matches) and assert, page by page, that the money and the actions
 * are IN the cards. The wide table is what every other suite in this
 * directory already renders, so the desktop is covered by all of them.
 */
import { Suspense } from "react";
import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/billing",
  useSearchParams: () => new URLSearchParams(),
}));

import * as api from "@/lib/api";
import BillingPage from "@/app/billing/page";
import ReceivablesPage from "@/app/receivables/page";
import RoutesPage from "@/app/routes/page";
import UsersPage from "@/app/admin/users/page";
import InvoiceDetailPage from "@/app/invoices/[id]/page";
import CustomerDetailPage from "@/app/customers/[id]/page";
import DeliveriesPage from "@/app/deliveries/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function phone() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query.includes("max-width"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

const SESSION = {
  authenticated: true,
  acting_tenant_id: null,
  user: { id: "u1", email: "owner@gavyam.example", full_name: "Owner", locale: "en", is_active: true },
  tenant_id: "org-1",
  organization: {
    id: "org-1", name: "Gavyam Dairy & Sweets", slug: "gavyam", country_code: "IN", currency_code: "INR",
    currency_symbol: "₹", timezone: "Asia/Kolkata", default_language: "en", supported_languages: ["en"],
    languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }], quantity_unit: "litre",
    quantity_unit_label: "L", modules: ["sales"], pay_to: "UPI gavyam@upi",
  },
  membership: null, roles: [], center_scope: null, permissions: ["*"],
};
const CUSTOMER = {
  id: "cu-1", code: "H-001", name: "Deshmukh household", customer_type: "household", phone: "+91 98765 43210",
  alternate_phone: "", address: "4 Hill Lane", notes: "", status: "active", billing_mode: "credit", billing_day: 1,
  currency: "INR", created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z",
};
const INVOICE = {
  id: "in-1", customer_id: "cu-1", invoice_number: "INV-2026-000001", period_from: "2026-08-01", period_to: "2026-08-31",
  currency: "INR", subtotal: "1860.00", adjustments: "0.00", total: "1860.00", previous_balance: "0.00",
  amount_due: "1860.00", status: "issued", line_count: 1, issued_at: "2026-09-01T03:00:00Z", created_at: "2026-09-01T03:00:00Z",
};
const DELIVERY = {
  id: "de-1", customer_id: "cu-1", delivery_date: "2026-08-11", slot: "morning", product: "COW-MILK", quantity: "2.000",
  quantity_unit: "L", unit_price: "62.0000", currency: "INR", amount: "124.00", status: "delivered", notes: "",
  invoice_id: null, plan_id: "ps-1", created_at: "2026-08-11T06:00:00Z",
};

type Handler = (path: string, init?: RequestInit) => Response | undefined;
function stub(handler: Handler) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    if (path.endsWith("/api/auth/session")) return json(SESSION);
    if (path.endsWith("/v1/auth/me")) return json(SESSION);
    return handler(path, init) ?? json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}
const mount = async (ui: React.ReactElement) => {
  await act(async () => {
    render(<Suspense fallback={null}>{ui}</Suspense>);
  });
};
/** The card that names this row, by text. */
const cardWith = async (text: RegExp | string) => {
  const cards = await screen.findAllByTestId("row-card");
  const card = cards.find((c) => (typeof text === "string" ? c.textContent?.includes(text) : text.test(c.textContent ?? "")));
  expect(card, `no card containing ${text}`).toBeDefined();
  return card!;
};
const moneyOf = (card: HTMLElement) => card.querySelector('[data-role="money"]')?.textContent ?? "";
const actionsOf = (card: HTMLElement) => card.querySelector('[data-role="actions"]') as HTMLElement;

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  phone();
});
afterEach(() => vi.unstubAllGlobals());

describe("money and actions are in the card, not off the right edge (WO-96 §1)", () => {
  it("/billing: the amount due beside the bill number, WhatsApp and Open at the bottom", async () => {
    stub((path) => {
      if (path.endsWith("/v1/invoices")) return json({ items: [INVOICE], total: 1, limit: 25, offset: 0 });
      if (path.endsWith("/v1/customers")) return json({ items: [CUSTOMER], total: 1, limit: 100, offset: 0 });
      if (path.endsWith("/v1/customers/payments") || path.endsWith("/v1/customers/receipts")) return json({ items: [], total: 0 });
      return undefined;
    });
    await mount(<BillingPage />);
    const card = await cardWith("INV-2026-000001");
    expect(moneyOf(card)).toMatch(/1,?860\.00/);
    expect(within(card).getByText("issued")).toBeInTheDocument();
    expect(within(actionsOf(card)).getByRole("link", { name: "Open" })).toBeInTheDocument();
    // The phone resolves a beat after the row (WO-83's `useCustomerPhones`).
    expect(await within(actionsOf(card)).findByTestId("whatsapp-INV-2026-000001")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("/receivables: what they owe, and Record payment at the bottom", async () => {
    stub((path) => {
      if (path.endsWith("/reports/receivables"))
        return json({
          items: [{ customer_id: "cu-1", code: "H-001", name: "Deshmukh household", phone: "+919876543210", status: "active", currency: "INR", invoiced: "5000.00", paid: "1000.00", outstanding: "4000.00", open_invoices: 1, last_payment_at: null, oldest_unpaid_from: "2026-07-01" }],
          total: 1, limit: 25, offset: 0, total_outstanding: "4000.00", currency: "INR",
        });
      return undefined;
    });
    await mount(<ReceivablesPage />);
    const card = await cardWith("Deshmukh household");
    expect(moneyOf(card)).toMatch(/4,?000\.00/);
    expect(within(actionsOf(card)).getByRole("link", { name: "Record payment" })).toBeInTheDocument();
  });

  it("/deliveries: the amount, the status and Correct in the card", async () => {
    stub((path) => {
      if (path.endsWith("/v1/deliveries")) return json({ items: [DELIVERY], total: 1, limit: 25, offset: 0, total_quantity: "2.000", total_amount: "124.00" });
      if (path.endsWith("/v1/deliveries/report")) return json({ date_from: "2026-08-05", date_to: "2026-08-12", currency: "INR", quantity_unit: "L", deliveries: 1, customers_served: 1, total_quantity: "2.000", total_amount: "124.00", skipped: 0, by_product: [], by_day: [] });
      if (path.endsWith("/v1/customers")) return json({ items: [CUSTOMER], total: 1, limit: 100, offset: 0 });
      if (path.endsWith("/v1/products")) return json({ items: [], total: 0 });
      if (path.endsWith("/v1/routes")) return json([]);
      if (path.includes("/v1/deliveries/generation-runs")) return json([]);
      if (path.endsWith("/v1/items")) return json({ items: [], total: 0, limit: 25, offset: 0 });
      return undefined;
    });
    await mount(<DeliveriesPage />);
    const card = await cardWith("2026-08-11");
    expect(moneyOf(card)).toMatch(/124\.00/);
    expect(within(card).getByText("delivered")).toBeInTheDocument();
    expect(actionsOf(card)).toBeTruthy();
  });

  it("/routes: driver, vehicle and the every-morning switch beneath the round's name", async () => {
    vi.spyOn(api, "listRoutes").mockResolvedValue([{ id: "route-1", code: "R-01", name: "Morning round", center_id: null, active: true, notes: "", default_driver_id: null, default_vehicle_id: null, auto_plan: false, stop_count: 3 }] as never);
    vi.spyOn(api, "listVehicles").mockResolvedValue([] as never);
    vi.spyOn(api, "listDrivers").mockResolvedValue([] as never);
    vi.spyOn(api, "listDeliveryRuns").mockResolvedValue([] as never);
    stub(() => undefined);
    await mount(<RoutesPage />);
    const card = await cardWith("R-01");
    expect(within(card).getByLabelText("Default delivery boy for R-01")).toBeInTheDocument();
    expect(within(card).getByLabelText("Default vehicle for R-01")).toBeInTheDocument();
    expect(within(card).getByLabelText("Plan R-01 every morning")).toBeInTheDocument();
  });

  it("/admin/users: Suspend, Deactivate and Remove are full-width buttons in the card", async () => {
    stub((path) => {
      if (path.endsWith("/v1/members")) return json([{ user_id: "u-2", status: "active", joined_at: "2026-09-01T00:00:00Z", roles: [{ name: "DRIVER", center_id: null }], pending_email_change: null }]);
      if (path.endsWith("/v1/identity/users/u-2")) return json({ id: "u-2", email: "raghvan@gavyam.example", full_name: "Raghvan", locale: "en", is_active: true, last_login_at: null, created_at: "2026-09-01T00:00:00Z" });
      if (path.includes("/v1/authz/roles")) return json([]);
      if (path.includes("/v1/collection-centers")) return json({ items: [], total: 0, limit: 100, offset: 0 });
      return undefined;
    });
    await mount(<UsersPage />);
    const card = await cardWith("Raghvan");
    const actions = actionsOf(card);
    for (const name of ["Suspend", "Deactivate", /Remove Raghvan from organisation/]) {
      expect(within(actions).getByRole("button", { name })).toBeInTheDocument();
    }
    expect(within(card).getByText("raghvan@gavyam.example")).toBeInTheDocument();
  });

  it("/invoices/[id]: every line's amount is in its card", async () => {
    stub((path) => {
      if (path.endsWith("/v1/invoices/in-1"))
        return json({ invoice: INVOICE, lines: [{ id: "il-1", delivery_id: "de-1", delivery_date: "2026-08-11", slot: "morning", product: "COW-MILK", product_name: "Cow milk", line_kind: "delivery", quantity: "2.000", quantity_unit: "L", unit_price: "62.0000", amount: "124.00", price_source: "plan" }], paid: "0.00", outstanding: "1860.00", totals_match_lines: true });
      if (path.endsWith("/v1/customers/cu-1")) return json({ customer: CUSTOMER, plans: [] });
      return undefined;
    });
    await mount(<InvoiceDetailPage params={Promise.resolve({ id: "in-1" })} />);
    const card = await cardWith("2026-08-11");
    expect(moneyOf(card)).toMatch(/124\.00/);
    expect(within(card).getByText(/milk · morning/)).toBeInTheDocument();
  });

  it("/customers/[id]: the delivery history's amount and status are in each card", async () => {
    stub((path) => {
      if (path.endsWith("/v1/customers/cu-1")) return json({ customer: CUSTOMER, plans: [] });
      if (path.endsWith("/v1/deliveries")) return json({ items: [DELIVERY], total: 1, limit: 25, offset: 0, total_quantity: "2.000", total_amount: "124.00" });
      if (path.endsWith("/v1/customers/cu-1/balance")) return json({ customer_id: "cu-1", currency: "INR", invoiced: "0.00", paid: "0.00", outstanding: "0.00", open_invoices: 0, unbilled_deliveries: 1, unbilled_amount: "124.00" });
      if (path.endsWith("/v1/customers/cu-1/statement")) return json({ customer_id: "cu-1", code: "H-001", name: "Deshmukh household", currency: "INR", date_from: "2026-09-01", date_to: "2026-09-25", opening_balance: "0.00", billed: "0.00", paid: "0.00", closing_balance: "0.00", entries: [] });
      if (path.endsWith("/v1/customers/cu-1/access")) return json({ login: null, bill_link: null });
      if (path.endsWith("/v1/invoices") || path.endsWith("/v1/customers/payments") || path.endsWith("/v1/customers/receipts") || path.endsWith("/v1/products") || path.endsWith("/v1/customers/cu-1/items")) return json({ items: [], total: 0, limit: 25, offset: 0 });
      return undefined;
    });
    await mount(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    const card = await cardWith("2026-08-11");
    expect(moneyOf(card)).toMatch(/124\.00/);
    expect(within(card).getByText("delivered")).toBeInTheDocument();
  });
});

describe("phones do not zoom on every field (WO-96 §2)", () => {
  const read = (rel: string) => readFileSync(resolve(__dirname, rel), "utf8");
  it("the shared input and select are 16px below md, and every hand-built textarea too", () => {
    for (const file of ["../components/ui/input.tsx", "../components/ui/select.tsx"]) {
      const src = read(file);
      expect(src, file).toMatch(/text-base/);
      expect(src, file).toMatch(/md:text-(sm|xs)/);
    }
    for (const file of ["admin/settings/page.tsx", "admin/configuration/page.tsx", "../components/rate-change.tsx", "../components/csv-import.tsx"]) {
      const src = read(file);
      for (const m of src.matchAll(/<textarea[\s\S]*?className="([^"]*)"/g)) {
        expect(m[1], `${file}: ${m[1]}`).toMatch(/\btext-base\b/);
      }
    }
  });
  it("never disables zoom for the people who need it", () => {
    const layout = read("layout.tsx");
    expect(layout).not.toMatch(/maximum-scale/);
    expect(layout).not.toMatch(/user-scalable=no/);
  });
});
