/**
 * The customer's own way in (WO-86): the two cards on the customer page, and
 * the public page a bill link opens.
 *
 *   * the login card reads the platform's state and invites by email — the
 *     code is never on this screen;
 *   * a pending invitation can be withdrawn or re-sent;
 *   * the bill-link card mints once, shows the URL ONCE with the trade-off
 *     text beside it, and revokes;
 *   * the public page shows the household's bills, receipts and statement,
 *     and one calm sentence for a dead link.
 */
import { Suspense } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/customers/cu-1",
  useSearchParams: () => new URLSearchParams(),
}));

import { CustomerAccessCards } from "@/components/customer-access";
import PublicBillPage from "@/app/bill/[token]/page";
import { metadata as billMetadata } from "@/app/bill/layout";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

type Handler = (path: string, init?: RequestInit) => Response | undefined;

function stub(handler: Handler) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    return handler(path, init) ?? json({ title: "not_found", detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const calls = (spy: ReturnType<typeof stub>) =>
  spy.mock.calls.map((c) => [String(c[0]), (c[1] as RequestInit | undefined)?.method ?? "GET"]);

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("the login card", () => {
  it("invites by email and never shows a code", async () => {
    let state: Record<string, unknown> = { customer_id: "cu-1", state: "none" };
    const spy = stub((path, init) => {
      if (path.endsWith("/v1/customers/cu-1/login")) return json(state);
      if (path.endsWith("/v1/customers/cu-1/bill-link"))
        return json({ customer_id: "cu-1", active: false });
      if (path.endsWith("/v1/customers/cu-1/invite") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { email: string };
        state = {
          customer_id: "cu-1",
          state: "invited",
          email: body.email,
          invitation_id: "inv-1",
          expires_at: "2026-10-02T00:00:00Z",
        };
        return json(state, 201);
      }
      return undefined;
    });
    const user = userEvent.setup();
    render(<CustomerAccessCards customerId="cu-1" />);
    const card = await screen.findByTestId("customer-login-card");
    // The card is on screen before its status has loaded ("Checking…"), so
    // this must wait for the answer rather than read the first paint.
    expect(await within(card).findByText(/No login yet/)).toBeInTheDocument();

    await user.type(within(card).getByLabelText("Household email"), "home@x.example");
    await user.click(within(card).getByRole("button", { name: "Invite" }));

    await waitFor(() =>
      expect(calls(spy)).toContainEqual([
        expect.stringMatching(/\/v1\/customers\/cu-1\/invite$/),
        "POST",
      ]),
    );
    const post = spy.mock.calls.find((c) => (c[1] as RequestInit)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ email: "home@x.example" });
    expect(await within(card).findByText(/Invitation sent to home@x.example/)).toBeInTheDocument();
    expect(within(card).getByText(/is not shown here/)).toBeInTheDocument();
    // A pending invitation offers withdrawal and re-sending; an active login offers neither.
    expect(within(card).getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Re-invite" })).toBeInTheDocument();
    expect(card.textContent).not.toMatch(/token/i);
  });

  it("withdraws a pending invitation, and an active login has nothing to press", async () => {
    let state: Record<string, unknown> = {
      customer_id: "cu-1",
      state: "invited",
      email: "home@x.example",
      invitation_id: "inv-1",
    };
    const spy = stub((path, init) => {
      if (path.endsWith("/v1/customers/cu-1/login")) return json(state);
      if (path.endsWith("/v1/customers/cu-1/bill-link"))
        return json({ customer_id: "cu-1", active: false });
      if (path.endsWith("/v1/customers/cu-1/invitation") && init?.method === "DELETE") {
        state = { customer_id: "cu-1", state: "none" };
        return new Response(null, { status: 204 });
      }
      return undefined;
    });
    const user = userEvent.setup();
    render(<CustomerAccessCards customerId="cu-1" />);
    const card = await screen.findByTestId("customer-login-card");
    await user.click(await within(card).findByRole("button", { name: "Withdraw" }));
    await waitFor(() =>
      expect(calls(spy)).toContainEqual([
        expect.stringMatching(/\/v1\/customers\/cu-1\/invitation$/),
        "DELETE",
      ]),
    );
    expect(await within(card).findByText(/No login yet/)).toBeInTheDocument();

    vi.unstubAllGlobals();
    stub((path) => {
      if (path.endsWith("/v1/customers/cu-2/login"))
        return json({ customer_id: "cu-2", state: "active", email: "live@x.example" });
      if (path.endsWith("/v1/customers/cu-2/bill-link"))
        return json({ customer_id: "cu-2", active: false });
      return undefined;
    });
    render(<CustomerAccessCards customerId="cu-2" />);
    const active = (await screen.findAllByTestId("customer-login-card")).at(-1)!;
    expect(await within(active).findByText(/Signed up as live@x.example/)).toBeInTheDocument();
    expect(within(active).queryByRole("button")).toBeNull();
  });
});

describe("the bill-link card", () => {
  it("mints once, shows the URL with the trade-off beside it, and revokes", async () => {
    let link: Record<string, unknown> = { customer_id: "cu-1", active: false };
    const spy = stub((path, init) => {
      if (path.endsWith("/v1/customers/cu-1/login"))
        return json({ customer_id: "cu-1", state: "none" });
      if (path.endsWith("/v1/customers/cu-1/bill-link") && init?.method === "POST") {
        link = {
          customer_id: "cu-1",
          active: true,
          created_at: "2026-09-25T00:00:00Z",
          expires_at: "2027-09-25T00:00:00Z",
        };
        return json({ ...link, token: "tok-secret-123" }, 201);
      }
      if (path.endsWith("/v1/customers/cu-1/bill-link") && init?.method === "DELETE") {
        link = { customer_id: "cu-1", active: false };
        return new Response(null, { status: 204 });
      }
      if (path.endsWith("/v1/customers/cu-1/bill-link")) return json(link);
      return undefined;
    });
    const user = userEvent.setup();
    render(<CustomerAccessCards customerId="cu-1" />);
    const card = await screen.findByTestId("customer-bill-link-card");
    // The trade-off is on the card before anything is made.
    expect(within(card).getByText(/Anyone who has this link can see this customer/)).toBeInTheDocument();
    expect(within(card).getByText(/replace it/)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Revoke" })).toBeNull();

    await user.click(await within(card).findByRole("button", { name: "Create link" }));
    const field = (await within(card).findByLabelText(/Copy it now/)) as HTMLInputElement;
    expect(field.value).toMatch(/\/bill\/tok-secret-123$/);
    expect(within(card).getByRole("button", { name: "Replace link" })).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(calls(spy)).toContainEqual([
        expect.stringMatching(/\/v1\/customers\/cu-1\/bill-link$/),
        "DELETE",
      ]),
    );
    expect(await within(card).findByRole("button", { name: "Create link" })).toBeInTheDocument();
    // The URL is gone with the link.
    expect(within(card).queryByLabelText(/Copy it now/)).toBeNull();
  });
});

describe("the public bill page", () => {
  const BILL = {
    organization: "Sitara Dairy",
    customer: { name: "Deshmukh household", code: "H-001", address: "12 Lake Road" },
    currency: "INR",
    balance: {
      customer_id: "cu-1",
      currency: "INR",
      invoiced: "3660.00",
      paid: "3000.00",
      outstanding: "660.00",
      open_invoices: 1,
      unbilled_deliveries: 4,
      unbilled_amount: "240.00",
    },
    invoices: [
      {
        id: "in-2",
        customer_id: "cu-1",
        invoice_number: "INV-2026-000002",
        period_from: "2026-08-01",
        period_to: "2026-08-31",
        currency: "INR",
        subtotal: "1860.00",
        adjustments: "0.00",
        total: "1860.00",
        previous_balance: "0.00",
        amount_due: "660.00",
        status: "issued",
        line_count: 31,
        issued_at: "2026-09-01T03:00:00Z",
        created_at: "2026-09-01T03:00:00Z",
        receipts: [
          {
            id: "rc-1",
            receipt_number: "RCT-2026-000009",
            payment_id: "pm-1",
            payment_number: "PAY-2026-000009",
            customer_id: "cu-1",
            customer_name: "Deshmukh household",
            customer_code: "H-001",
            amount: "1200.00",
            currency: "INR",
            method: "UPI",
            reference: "",
            applied_to: "INV-2026-000002",
            generated_at: "2026-09-03T10:00:00Z",
          },
        ],
      },
    ],
    statement: {
      customer_id: "cu-1",
      code: "H-001",
      name: "Deshmukh household",
      currency: "INR",
      date_from: "2026-09-01",
      date_to: "2026-09-25",
      opening_balance: "1860.00",
      billed: "0.00",
      paid: "1200.00",
      closing_balance: "660.00",
      entries: [
        {
          entry_date: "2026-09-03",
          kind: "payment",
          reference: "PAY-2026-000009",
          detail: "UPI",
          debit: "0.00",
          credit: "1200.00",
          balance: "660.00",
          receipt_number: "RCT-2026-000009",
        },
      ],
    },
    generated_at: "2026-09-25T06:00:00Z",
  };

  it("shows the household's bills, receipts and statement from the public handler alone", async () => {
    const spy = stub((path) => (path === "/api/public/bill/tok-1" ? json(BILL) : undefined));
    await act(async () => {
      render(
        <Suspense fallback={<span>loading…</span>}>
          <PublicBillPage params={Promise.resolve({ token: "tok-1" })} />
        </Suspense>,
      );
    });
    expect(await screen.findByText("Deshmukh household")).toBeInTheDocument();
    expect(screen.getByText("Sitara Dairy")).toBeInTheDocument();
    expect(screen.getByTestId("public-bill-outstanding").textContent).toMatch(/660/);
    const invoice = screen.getByTestId("public-invoice-INV-2026-000002");
    expect(within(invoice).getByText(/Receipt RCT-2026-000009/)).toBeInTheDocument();
    expect(screen.getByText(/receipt RCT-2026-000009/)).toBeInTheDocument();
    // Only the public handler was asked; no proxy, no session probe.
    const urls = calls(spy).map(([u]) => u);
    expect(urls).toEqual(["/api/public/bill/tok-1"]);
    expect(screen.getByText(/private to whoever holds its link/)).toBeInTheDocument();
  });

  it("says one calm sentence for a dead link", async () => {
    stub(() => json({ title: "not_found", detail: "bill link not found" }, 404));
    await act(async () => {
      render(
        <Suspense fallback={<span>loading…</span>}>
          <PublicBillPage params={Promise.resolve({ token: "dead" })} />
        </Suspense>,
      );
    });
    expect(await screen.findByText("This link does not open a bill")).toBeInTheDocument();
    expect(screen.getByText(/Ask them for a new link/)).toBeInTheDocument();
  });

  it("is kept out of search indexes", () => {
    expect(billMetadata.robots).toMatchObject({ index: false, follow: false });
  });
});
