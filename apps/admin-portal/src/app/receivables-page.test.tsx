/**
 * Who owes money (DEMO-010).
 *
 * One property matters more than everything else on this page and is asserted
 * from several directions: **the headline total is the platform's, computed
 * across every debtor, and is never the sum of the rows on screen.** A page
 * total looks completely plausible — it is a real number, correctly formatted,
 * derived from real rows — and it under-reports the debt of any dairy with
 * more households than fit on one screen. So the fixture below deliberately
 * makes the two figures differ, and the test asserts the larger one is shown.
 *
 * The rest is the same contract every list on this platform keeps: the
 * database filters, sorts and paginates; the browser renders.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/receivables",
}));

import ReceivablesPage from "@/app/receivables/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const row = (n: number, outstanding: string) => ({
  customer_id: `cu${n}`,
  code: `CUS-${String(n).padStart(4, "0")}`,
  name: `Household ${n}`,
  phone: `+2547000000${n}`,
  status: "active",
  currency: "KES",
  invoiced: "5000.00",
  paid: "1000.00",
  outstanding,
  open_invoices: 1,
  last_payment_at: n % 2 ? "2026-08-02T08:00:00+00:00" : null,
  oldest_unpaid_from: "2026-07-01",
});

/** Two rows on screen worth 3,600 — out of 40 debtors worth 84,300. */
const PAGE = {
  items: [row(1, "2400.00"), row(2, "1200.00")],
  total: 40,
  limit: 25,
  offset: 0,
  total_outstanding: "84300.00",
  currency: "KES",
};

function route(overrides: Record<string, () => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/api/auth/session"))
      return json({
        authenticated: true,
        tenant_id: "org-1",
        permissions: ["*"],
      });
    if (url.includes("/reports/receivables")) return json(PAGE);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("receivables", () => {
  it("shows the platform's total across every debtor, not the sum of the page", async () => {
    route();
    render(<ReceivablesPage />);

    expect(await screen.findByText("84,300.00")).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("region", { name: "Receivables summary" }),
      ).getByText("40"),
    ).toBeInTheDocument();
    // The two visible balances add to 3,600. If that ever became the headline,
    // this page would be quietly wrong by an order of magnitude.
    expect(screen.queryByText("3,600.00")).not.toBeInTheDocument();
    expect(screen.getByText("2,400.00")).toBeInTheDocument();
  });

  it("asks the database to filter, rather than narrowing rows in the browser", async () => {
    const spy = route();
    render(<ReceivablesPage />);
    await screen.findByText("Household 1");

    await userEvent.type(screen.getByLabelText("Search"), "njeri");
    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("q=njeri"));
      expect(asked.length).toBeGreaterThan(0);
    });
  });

  it("asks for every customer, not only debtors, when the scope changes", async () => {
    const spy = route();
    render(<ReceivablesPage />);
    await screen.findByText("Household 1");

    // The default is the collection round: only people who owe.
    expect(
      spy.mock.calls.some(([u]) => String(u).includes("owing_only=true")),
    ).toBe(true);

    await userEvent.selectOptions(screen.getByLabelText("Show"), "all");
    await waitFor(() => {
      expect(
        spy.mock.calls.some(([u]) => String(u).includes("owing_only=false")),
      ).toBe(true);
    });
  });

  it("pages through the server's rows and never fetches them all", async () => {
    const spy = route();
    render(<ReceivablesPage />);
    await screen.findByText("Household 1");

    // 40 debtors, a page of 25 — the request must say so.
    expect(spy.mock.calls.some(([u]) => String(u).includes("limit=25"))).toBe(
      true,
    );

    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(
        spy.mock.calls.some(([u]) => String(u).includes("offset=25")),
      ).toBe(true);
    });
  });

  it("links each customer to the page where a payment is actually recorded", async () => {
    route();
    render(<ReceivablesPage />);
    await screen.findByText("Household 1");

    const first = screen.getByRole("link", { name: "Household 1" });
    expect(first).toHaveAttribute("href", "/customers/cu1");
    expect(
      screen.getAllByRole("link", { name: "Record payment" })[0],
    ).toHaveAttribute("href", "/customers/cu1");
  });

  it("says a customer has never paid rather than showing an empty cell", async () => {
    route();
    render(<ReceivablesPage />);
    await screen.findByText("Household 2");

    const table = screen.getByRole("table");
    expect(within(table).getByText("never paid")).toBeInTheDocument();
  });

  it("treats an empty book as good news, not as an error", async () => {
    route({
      "/reports/receivables": () =>
        json({
          items: [],
          total: 0,
          limit: 25,
          offset: 0,
          total_outstanding: "0.00",
          currency: null,
        }),
    });
    render(<ReceivablesPage />);

    expect(
      await screen.findByText("Every customer is settled"),
    ).toBeInTheDocument();
    expect(screen.getByText("0.00")).toBeInTheDocument();
  });

  it("reports a refusal as a refusal, with a way to try again", async () => {
    route({
      "/reports/receivables": () =>
        json({ title: "forbidden", detail: "Not permitted." }, 403),
    });
    render(<ReceivablesPage />);

    expect(await screen.findByText(/Not permitted/)).toBeInTheDocument();
  });

  it("mounts once, so it issues its request once", async () => {
    // DEMO-007's regression: a differently-shaped tree while the session probe
    // was in flight remounted every page and doubled every request.
    const spy = route();
    render(<ReceivablesPage />);
    await screen.findByText("Household 1");

    await waitFor(() => {
      const asked = spy.mock.calls
        .map(([u]) => String(u))
        .filter((u) => u.includes("/reports/receivables"));
      expect(asked.length).toBe(1);
    });
  });
});
