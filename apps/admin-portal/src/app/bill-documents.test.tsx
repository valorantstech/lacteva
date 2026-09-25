/**
 * The bill as a thing you can hand over (WO-83).
 *
 *   * Admin → Settings has the address, phone and "Pay to" line, saved through
 *     the locale settings the platform already owns;
 *   * the invoice page can print, download the platform's PDF, and open a
 *     WhatsApp link with the summary typed — or says plainly why it cannot;
 *   * Billing issues every draft for a period in one act, behind a confirm
 *     that shows the PLATFORM's count and total, and lists the exceptions;
 *   * a household in credit reads "Advance", never a negative debt, on the
 *     statement and on the public bill;
 *   * the public bill carries the dairy's head and "Pay to".
 *
 * Nothing here sums money: every figure asserted came back from the stub.
 */
import { Suspense } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/billing",
  useSearchParams: () => new URLSearchParams(),
}));

import BillingPage from "@/app/billing/page";
import InvoiceDetailPage from "@/app/invoices/[id]/page";
import PublicBillPage from "@/app/bill/[token]/page";
import CustomerDetailPage from "@/app/customers/[id]/page";
import OrganizationSettingsPage from "@/app/admin/settings/page";
import type { Invoice, Me, Session } from "@/lib/api";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const ORGANIZATION = {
  id: "org-1",
  name: "Sitara Dairy",
  slug: "sitara",
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
  address: "12 Lake Road, Pune",
  phone: "+919800000001",
  pay_to: "UPI sitara@upi",
};

const ME: Me = {
  user: { id: "u1", email: "owner@sitara.example", full_name: "Owner", locale: "en", is_active: true },
  tenant_id: "org-1",
  organization: ORGANIZATION,
  membership: null,
  roles: [{ name: "tenant-admin", description: "", center_id: null }],
  center_scope: null,
  permissions: ["*"],
};

const SESSION: Session = { authenticated: true, acting_tenant_id: null, ...ME };

const LOCALE = {
  country_code: "IN",
  country_name: "India",
  currency_code: "INR",
  currency_symbol: "₹",
  timezone: "Asia/Kolkata",
  default_language: "en",
  supported_languages: ["en"],
  languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
  quantity_unit: "litre",
  quantity_unit_label: "L",
  units: ["litre", "kg"],
  trade_unit: null,
  trade_unit_label: null,
  conversion_factor: null,
  conversion_effective_from: null,
  modules: ["collection", "sales"],
  available_modules: [
    { key: "collection", label: "collects", description: "in" },
    { key: "sales", label: "sells", description: "out" },
  ],
  address: "",
  phone: "",
  pay_to: "",
};

const customer = (over: Partial<typeof CUSTOMER> = {}) => ({ ...CUSTOMER, ...over });
const CUSTOMER = {
  id: "cu-1",
  code: "H-001",
  name: "Deshmukh household",
  customer_type: "household",
  phone: "+91 98765 43210",
  alternate_phone: "",
  address: "4 Hill Lane",
  notes: "",
  status: "active",
  billing_mode: "credit",
  billing_day: 1,
  currency: "INR",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const invoice = (over: Partial<Invoice> = {}): Invoice => ({ ...INVOICE, ...over });
const INVOICE: Invoice = {
  id: "in-1",
  customer_id: "cu-1",
  invoice_number: "INV-2026-000001",
  period_from: "2026-08-01",
  period_to: "2026-08-31",
  currency: "INR",
  subtotal: "1860.00",
  adjustments: "0.00",
  total: "1860.00",
  previous_balance: "0.00",
  amount_due: "1860.00",
  status: "issued",
  line_count: 31,
  issued_at: "2026-09-01T03:00:00Z",
  created_at: "2026-09-01T03:00:00Z",
};

const STATEMENT = {
  customer_id: "cu-1",
  code: "H-001",
  name: "Deshmukh household",
  currency: "INR",
  date_from: "2026-09-01",
  date_to: "2026-09-25",
  opening_balance: "-412.00",
  billed: "0.00",
  paid: "0.00",
  closing_balance: "-412.00",
  entries: [],
};

type Handler = (path: string, url: string, init?: RequestInit) => Response | undefined;

function stub(handler: Handler) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    if (path.endsWith("/api/auth/session")) return json(SESSION);
    if (path.endsWith("/v1/auth/me")) return json(ME);
    return handler(path, url, init) ?? json({ title: "not_found", detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const mount = async (ui: React.ReactElement) => {
  await act(async () => {
    render(<Suspense fallback={<span>loading…</span>}>{ui}</Suspense>);
  });
};

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("Admin → Settings: the head of every bill (WO-83 §2a)", () => {
  it("shows the three fields and sends them through the locale settings", async () => {
    const spy = stub((path, _url, init) => {
      if (path.endsWith("/v1/organizations/settings/locale") && init?.method === "PUT")
        return json({ ...LOCALE, ...JSON.parse(String(init.body)) });
      if (path.endsWith("/v1/organizations/settings/locale")) return json(LOCALE);
      return undefined;
    });
    const user = userEvent.setup();
    render(<OrganizationSettingsPage />);
    const section = await screen.findByTestId("org-contact");
    await user.type(within(section).getByLabelText("Address"), "12 Lake Road, Pune");
    await user.type(within(section).getByLabelText("Phone"), "+919800000001");
    await user.type(within(section).getByLabelText("Pay to"), "UPI sitara@upi");
    await user.click(within(section).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(spy.mock.calls.some((c) => (c[1] as RequestInit)?.method === "PUT")).toBe(true),
    );
    const put = spy.mock.calls.find((c) => (c[1] as RequestInit)?.method === "PUT")!;
    expect(JSON.parse(String((put[1] as RequestInit).body))).toEqual({
      address: "12 Lake Road, Pune",
      phone: "+919800000001",
      pay_to: "UPI sitara@upi",
    });
  });
});

describe("the invoice page: print, download, WhatsApp, advance (WO-83 §2, §3)", () => {
  const detail = (inv = INVOICE) => ({
    invoice: inv,
    lines: [],
    paid: "0.00",
    outstanding: inv.amount_due,
    totals_match_lines: true,
  });

  it("downloads the platform's PDF, prints, and opens wa.me with the summary typed", async () => {
    stub((path) => {
      if (path.endsWith("/v1/invoices/in-1")) return json(detail());
      if (path.endsWith("/v1/customers/cu-1")) return json({ customer: CUSTOMER, plans: [] });
      return undefined;
    });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    const user = userEvent.setup();
    await mount(<InvoiceDetailPage params={Promise.resolve({ id: "in-1" })} />);
    await screen.findAllByText("INV-2026-000001");

    const download = screen.getByRole("link", { name: /Download PDF/ });
    expect(download.getAttribute("href")).toBe("/api/proxy/v1/invoices/in-1/pdf");
    expect(download.hasAttribute("download")).toBe(true);

    await user.click(screen.getByRole("button", { name: /Print/ }));
    expect(print).toHaveBeenCalledTimes(1);

    const send = await screen.findByTestId("whatsapp-send");
    const href = send.getAttribute("href")!;
    // The phone is E.164 digits with the spaces and the plus gone …
    expect(href.startsWith("https://wa.me/919876543210?text=")).toBe(true);
    // … and the summary names the dairy, the bill, the platform's amount and how to pay.
    const text = decodeURIComponent(href.split("text=")[1]);
    expect(text).toContain("Sitara Dairy");
    expect(text).toContain("INV-2026-000001");
    expect(text).toContain("1860.00");
    expect(text).toContain("UPI sitara@upi");
    expect(send.getAttribute("target")).toBe("_blank");
  });

  it("with no phone: the control is disabled and says why", async () => {
    stub((path) => {
      if (path.endsWith("/v1/invoices/in-1")) return json(detail());
      if (path.endsWith("/v1/customers/cu-1"))
        return json({ customer: customer({ phone: "" }), plans: [] });
      return undefined;
    });
    await mount(<InvoiceDetailPage params={Promise.resolve({ id: "in-1" })} />);
    await screen.findAllByText("INV-2026-000001");
    const disabled = await screen.findByTestId("whatsapp-disabled");
    await waitFor(() => expect(disabled.textContent).toMatch(/no phone on this customer/));
    expect(within(disabled).getByRole("button", { name: /Send on WhatsApp/ })).toBeDisabled();
    expect(screen.queryByTestId("whatsapp-send")).toBeNull();
  });

  it("a household in credit reads Advance, not a negative debt", async () => {
    stub((path) => {
      if (path.endsWith("/v1/invoices/in-1"))
        return json(detail(invoice({ previous_balance: "-412.00", amount_due: "1448.00" })));
      if (path.endsWith("/v1/customers/cu-1")) return json({ customer: CUSTOMER, plans: [] });
      return undefined;
    });
    await mount(<InvoiceDetailPage params={Promise.resolve({ id: "in-1" })} />);
    await screen.findAllByText("INV-2026-000001");
    expect(screen.getByText("Advance")).toBeInTheDocument();
    expect(screen.queryByText("Brought forward")).toBeNull();
    expect(screen.queryByText(/-412/)).toBeNull();
    expect(screen.getAllByText(/412\.00/).length).toBeGreaterThan(0);
  });
});

describe("Billing: Issue all (WO-83 §1) and the row's WhatsApp (§3)", () => {
  const PREVIEW = {
    preview: true,
    period_from: "2026-08-01",
    period_to: "2026-08-31",
    issued: [
      { invoice_id: "in-1", invoice_number: "INV-2026-000001", customer_id: "cu-1", currency: "INR", amount_due: "1860.00" },
      { invoice_id: "in-2", invoice_number: "INV-2026-000002", customer_id: "cu-2", currency: "INR", amount_due: "940.00" },
    ],
    skipped: [],
    currency: "INR",
    total: "2800.00",
  };
  const DONE = {
    ...PREVIEW,
    preview: false,
    issued: [PREVIEW.issued[0]],
    skipped: [{ ...PREVIEW.issued[1], reason: "totals do not match the lines" }],
    total: "1860.00",
  };

  function billing() {
    const batch: unknown[] = [];
    const spy = stub((path, _url, init) => {
      if (path.endsWith("/v1/invoices/issue-batch")) {
        const body = JSON.parse(String(init?.body));
        batch.push(body);
        return json(body.preview ? PREVIEW : DONE);
      }
      if (path.endsWith("/v1/invoices"))
        return json({
          items: [
            invoice({ status: "draft", issued_at: null }),
            invoice({ id: "in-2", customer_id: "cu-2", invoice_number: "INV-2026-000002", status: "draft", issued_at: null }),
          ],
          total: 2,
          limit: 25,
          offset: 0,
        });
      if (path.endsWith("/v1/customers"))
        return json({
          items: [CUSTOMER, customer({ id: "cu-2", code: "H-002", name: "Patil household", phone: "" })],
          total: 2,
          limit: 100,
          offset: 0,
        });
      if (path.endsWith("/v1/customers/payments")) return json({ items: [], total: 0 });
      if (path.endsWith("/v1/customers/receipts")) return json({ items: [], total: 0 });
      return undefined;
    });
    return { spy, batch };
  }

  it("previews first, confirms with the platform's count and total, then lists the exceptions", async () => {
    const { batch } = billing();
    const user = userEvent.setup();
    await mount(<BillingPage />);
    await screen.findByText("INV-2026-000001");

    await user.click(screen.getByRole("button", { name: "Issue all drafts…" }));
    await user.click(screen.getByRole("button", { name: "Count the drafts" }));
    const confirm = await screen.findByTestId("issue-all-confirm");
    expect(batch).toHaveLength(1);
    expect(batch[0]).toMatchObject({ preview: true });
    expect(confirm.textContent).toMatch(/2 drafts will be issued/);
    expect(confirm.textContent).toMatch(/2,?800\.00/);

    await user.click(within(confirm).getByRole("button", { name: "Issue all 2" }));
    const result = await screen.findByTestId("issue-all-result");
    expect(batch).toHaveLength(2);
    expect(batch[1]).not.toHaveProperty("preview");
    expect(result.textContent).toMatch(/Issued 1/);
    expect(result.textContent).toMatch(/INV-2026-000002: totals do not match the lines/);
  });

  it("each row has a WhatsApp link for a customer with a phone, and an honest blank for one without", async () => {
    billing();
    await mount(<BillingPage />);
    await screen.findByText("INV-2026-000001");
    const link = await screen.findByTestId("whatsapp-INV-2026-000001");
    expect(link.getAttribute("href")!.startsWith("https://wa.me/919876543210?text=")).toBe(true);
    expect(screen.getByTestId("whatsapp-none-INV-2026-000002")).toBeInTheDocument();
  });
});

describe("the statement and the public bill say Advance (WO-83 §2b)", () => {
  it("the customer page labels a credit opening balance Advance and links the statement PDF", async () => {
    stub((path) => {
      if (path.endsWith("/v1/customers/cu-1")) return json({ customer: CUSTOMER, plans: [] });
      if (path.endsWith("/v1/customers/cu-1/statement")) return json(STATEMENT);
      if (path.endsWith("/v1/customers/cu-1/balance"))
        return json({
          customer_id: "cu-1",
          currency: "INR",
          invoiced: "0.00",
          paid: "412.00",
          outstanding: "-412.00",
          open_invoices: 0,
          unbilled_deliveries: 0,
          unbilled_amount: "0.00",
        });
      if (path.endsWith("/v1/customers/cu-1/access")) return json({ login: null, bill_link: null });
      if (path.endsWith("/v1/deliveries")) return json({ items: [], total: 0, limit: 25, offset: 0 });
      if (path.endsWith("/v1/invoices")) return json({ items: [], total: 0, limit: 25, offset: 0 });
      if (path.endsWith("/v1/customers/payments")) return json({ items: [], total: 0 });
      if (path.endsWith("/v1/customers/receipts")) return json({ items: [], total: 0 });
      if (path.endsWith("/v1/products")) return json({ items: [], total: 0 });
      if (path.endsWith("/v1/customers/cu-1/items")) return json({ items: [], total: 0 });
      return undefined;
    });
    await mount(<CustomerDetailPage params={Promise.resolve({ id: "cu-1" })} />);
    expect(await screen.findByText("Advance")).toBeInTheDocument();
    expect(screen.queryByText("Opening balance")).toBeNull();
    const pdf = screen.getByRole("link", { name: "Download statement (PDF)" });
    expect(pdf.getAttribute("href")).toBe(
      "/api/proxy/v1/customers/cu-1/statement.pdf?date_from=2026-09-01&date_to=2026-09-25",
    );
  });

  it("the public bill carries the dairy's head, Pay to, and Advance held", async () => {
    stub((path) =>
      path === "/api/public/bill/tok-1"
        ? json({
            organization: "Sitara Dairy",
            organization_address: "12 Lake Road, Pune",
            organization_phone: "+919800000001",
            pay_to: "UPI sitara@upi",
            customer: { name: "Deshmukh household", code: "H-001", address: "4 Hill Lane" },
            currency: "INR",
            balance: {
              customer_id: "cu-1",
              currency: "INR",
              invoiced: "0.00",
              paid: "412.00",
              outstanding: "-412.00",
              open_invoices: 0,
              unbilled_deliveries: 0,
              unbilled_amount: "0.00",
            },
            invoices: [],
            statement: STATEMENT,
            generated_at: "2026-09-25T06:00:00Z",
          })
        : undefined,
    );
    await mount(<PublicBillPage params={Promise.resolve({ token: "tok-1" })} />);
    await screen.findByText("Deshmukh household");
    expect(screen.getByTestId("public-bill-head").textContent).toBe("12 Lake Road, Pune · +919800000001");
    expect(screen.getByTestId("public-bill-pay-to").textContent).toContain("UPI sitara@upi");
    expect(screen.getByText("Advance held")).toBeInTheDocument();
    expect(screen.queryByText("You owe")).toBeNull();
    expect(screen.getByTestId("public-bill-outstanding").textContent).not.toMatch(/-/);
    expect(screen.getByText(/advance/)).toBeInTheDocument();
  });
});
