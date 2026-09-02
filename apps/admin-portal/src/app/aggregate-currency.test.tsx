/**
 * A total may never wear the wrong currency (WO-61 · LACTEVA-BACKEND-007).
 *
 * The owner's screenshot, as tests. Signed into a demo dairy, /settlements
 * listed four settlements of 3,600.00 + 450.00 + 450.00 + 5,647.50 **KES**
 * and headed them with a "Finalized value" tile reading their exact sum,
 * 10,147.50, labelled **INR** — because the tile took its currency from the
 * ORGANIZATION while the rows carried their own.
 *
 * What is pinned here is the rule, not the incident: a rendered total is
 * denominated by the platform's answer, and this client no longer has a way
 * to denominate one for itself.
 */
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/settlements",
  useSearchParams: () => new URLSearchParams(),
}));

import SettlementsPage from "@/app/settlements/page";
import PaymentsPage from "@/app/payments/page";
import { CurrencyTotals } from "@/components/money";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** The live shape: an Indian organization holding Kenyan money. */
const SETTLEMENT_REPORT = {
  by_status: [
    { status: "finalized", count: 4, net_amount: "10147.50", currency: "KES" },
  ],
  finalized_by_currency: { KES: "10147.50" },
  total_settlements: 4,
  total_lines: 12,
};

const PAYMENT_REPORT = {
  by_status: [
    { status: "completed", count: 2, amount: "3600.00", currency: "KES" },
  ],
  total_payments: 2,
  completed_count: 2,
  processing_count: 0,
  pending_count: 0,
  failed_count: 0,
  completed_by_currency: { KES: "3600.00" },
  outstanding_by_currency: {},
  failed_by_currency: {},
  total_by_currency: { KES: "3600.00" },
};

function routeAll(overrides: Record<string, () => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/api/auth/session"))
      return json({
        authenticated: true,
        acting_tenant_id: "org-1",
        tenant_id: "org-1",
        permissions: ["*"],
        user: { id: "u1", email: "owner@example.com", full_name: "Owner" },
        // The organization says RUPEES. Every figure below is in shillings.
        organization: {
          id: "org-1",
          name: "Phoenix Demo Dairy",
          slug: "phoenix-demo",
          country_code: "IN",
          currency_code: "INR",
          currency_symbol: "₹",
          timezone: "Asia/Kolkata",
          default_language: "en-IN",
          supported_languages: ["en-IN"],
          languages: [],
        },
      });
    if (url.includes("/reports/settlements")) return json(SETTLEMENT_REPORT);
    if (url.includes("/reports/payments")) return json(PAYMENT_REPORT);
    if (url.includes("/v1/settlements"))
      return json({ items: [], total: 0, limit: 25, offset: 0 });
    if (url.includes("/v1/payments"))
      return json({ items: [], total: 0, limit: 25, offset: 0 });
    if (url.includes("/v1/suppliers"))
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    if (url.includes("/collection-centers"))
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("a total wears the currency of the rows it sums", () => {
  it("labels the finalized settlement value KES inside an INR organization", async () => {
    routeAll();
    render(<SettlementsPage />);

    const total = await screen.findByText("10,147.50");
    // The exact defect: this read INR beside four rows of KES.
    expect(total.parentElement).toHaveTextContent("KES");
    expect(total.parentElement).not.toHaveTextContent("INR");
  });

  it("labels every payment total from the payments, not the organization", async () => {
    routeAll();
    render(<PaymentsPage />);

    const paid = await screen.findByText("3,600.00");
    expect(paid.parentElement).toHaveTextContent("KES");
    expect(document.body).not.toHaveTextContent("INR");
  });
});

describe("CurrencyTotals, the component that made the class impossible", () => {
  it("renders one labelled figure for one currency", () => {
    render(<CurrencyTotals totals={{ KES: "10147.50" }} />);
    expect(screen.getByText("10,147.50").parentElement).toHaveTextContent("KES");
  });

  it("renders a figure PER currency rather than one number, for a mixed tenant", () => {
    // Adding shillings to rupees is a category error, not an arithmetic one.
    const { container } = render(
      <CurrencyTotals totals={{ KES: "10147.50", INR: "271796.50" }} />,
    );
    expect(within(container).getByText("10,147.50")).toBeInTheDocument();
    expect(within(container).getByText("271,796.50")).toBeInTheDocument();
    expect(container.textContent).not.toContain("281944.00");
  });

  it("says nothing rather than naming a currency it was not given", () => {
    const { container } = render(<CurrencyTotals totals={{}} />);
    expect(container.textContent).toBe("—");
  });
});
