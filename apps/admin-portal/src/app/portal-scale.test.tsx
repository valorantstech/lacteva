/**
 * Scale honesty on the list and report pages (P1-PORTAL-SCALE-001).
 *
 * The audit's findings this file pins:
 *   1. names come from resolving EXACTLY the ids on the page (`?ids=…`) — no
 *      100-row prefetch whose 101st farmer rendered as a UUID fragment;
 *   2. an id the platform does not return keeps its honest truncated
 *      fallback — never a fabricated name;
 *   3. reports page the platform: the count shown is the server's total and
 *      page two exists — a 120-supplier dairy no longer sees 50 rows dressed
 *      up as everything.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/transactions",
  useSearchParams: () => new URLSearchParams(),
}));

import ReportsPage from "@/app/reports/page";
import TransactionsPage from "@/app/transactions/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const tx = (n: number, supplierId: string | null) => ({
  id: `tx-${n}`,
  session_id: "ses-1",
  center_id: "c1",
  supplier_id: supplierId,
  operator_id: "op-1",
  state: "COMPLETED",
  milk_type: "cow",
  milk_type_custom: null,
  container_type: "can",
  container_identifier: null,
  arrival_temperature_c: null,
  arrived_at: null,
  weight_unit: "kg",
  gross_weight: 12,
  tare_weight: 2,
  net_weight: 10,
  fat_percentage: 4.1,
  snf_percentage: 8.6,
  clr_value: null,
  quality_grade: null,
  unit_price: "45.00",
  gross_amount: "450.00",
  currency: "INR",
  pricing_status: "PRICED",
  rejection_reason: null,
  slip_number: `SLP-2026-00000${n}`,
  created_at: "2026-08-19T06:10:00+00:00",
  updated_at: "2026-08-19T06:20:00+00:00",
});

const supplierRow = (n: number) => ({
  supplier_id: `sup-${n}`,
  supplier_code: `SUP-${String(n).padStart(3, "0")}`,
  supplier_name: `Milk Producer ${n}`,
  deliveries: 4,
  accepted: 4,
  total_net_weight_kg: 40,
  payable_amount: "1800.00",
  currency: "INR",
  weighted_avg_fat: 4.2,
});

afterEach(() => vi.unstubAllGlobals());

describe("transactions page name resolution", () => {
  function route() {
    const calls: string[] = [];
    const spy = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      const path = url.split("?")[0];
      if (path.endsWith("/v1/milk-transactions"))
        return json({
          items: [tx(1, "sup-7"), tx(2, "sup-unknown")],
          total: 2,
          limit: 20,
          offset: 0,
        });
      if (path.endsWith("/v1/suppliers")) {
        // The platform answers `ids` with the rows it actually has — the
        // unknown id simply is not among them (foreign or deleted).
        const ids = new URLSearchParams(url.split("?")[1] ?? "").getAll("ids");
        return json({
          items: ids
            .filter((id) => id === "sup-7")
            .map((id) => ({
              id,
              code: "SUP-007",
              status: "active",
              branch_id: null,
              full_name: "Ram Kumar",
              phone: "+911234567890",
            })),
          total: ids.includes("sup-7") ? 1 : 0,
          limit: 100,
          offset: 0,
        });
      }
      if (path.endsWith("/v1/centers"))
        return json({ items: [], total: 0, limit: 100, offset: 0 });
      // operational status, daily report, anything else: calm empties.
      return json({ items: [], total: 0 });
    });
    vi.stubGlobal("fetch", spy);
    return { spy, calls };
  }

  it("resolves the page's ids in one batch and never prefetches a capped list", async () => {
    const { calls } = route();
    render(<TransactionsPage />);

    // The resolved name appears…
    expect(await screen.findByText("Ram Kumar")).toBeInTheDocument();
    // …the unknown id stays an honest fragment, not an invented name…
    expect(screen.getByText(/sup-unkn/)).toBeInTheDocument();

    // …and the supplier directory was consulted ONLY via ?ids=…, never as a
    // 100-row prefetch (the audit's defect).
    const supplierCalls = calls.filter((u) => u.includes("/v1/suppliers?"));
    expect(supplierCalls.length).toBeGreaterThan(0);
    for (const u of supplierCalls) {
      expect(u).toContain("ids=");
      expect(u).not.toContain("limit=100");
    }
  });
});

describe("reports page pagination", () => {
  function route() {
    const supplierCalls: URLSearchParams[] = [];
    const all = Array.from({ length: 120 }, (_, i) => supplierRow(i + 1));
    const spy = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.split("?")[0];
      const params = new URLSearchParams(url.split("?")[1] ?? "");
      if (path.endsWith("/v1/reports/collection/by-supplier")) {
        supplierCalls.push(params);
        const offset = Number(params.get("offset") ?? 0);
        const limit = Number(params.get("limit") ?? 20);
        return json({
          items: all.slice(offset, offset + limit),
          total: all.length,
          limit,
          offset,
        });
      }
      if (path.endsWith("/v1/reports/collection/by-center"))
        return json({ items: [], total: 0, limit: 50, offset: 0 });
      if (path.endsWith("/v1/reports/collection/daily"))
        return json({
          date_from: "2026-08-19",
          date_to: "2026-08-19",
          transactions: 0,
          accepted: 0,
          rejected: 0,
          cancelled: 0,
          in_progress: 0,
          suppliers_served: 0,
          total_net_weight_kg: 0,
          payable_by_currency: {},
          unpriced_accepted: 0,
          weighted_avg_fat: null,
          weighted_avg_snf: null,
        });
      if (path.endsWith("/v1/reports/settlements"))
        return json({
          by_status: [],
          finalized_net_total: "0.00",
          total_settlements: 0,
          total_lines: 0,
        });
      if (path.endsWith("/v1/reports/pricing"))
        return json({
          priced_transactions: 0,
          unpriced_transactions: 0,
          min_unit_price: null,
          avg_unit_price: null,
          max_unit_price: null,
          gross_by_currency: {},
          published_rate_cards: 0,
          active_matrices: 0,
          active_bands: 0,
        });
      return json({ items: [], total: 0 });
    });
    vi.stubGlobal("fetch", spy);
    return { supplierCalls };
  }

  it("shows the server's total and reaches rows past the old 50-row cut", async () => {
    const { supplierCalls } = route();
    const user = userEvent.setup();
    render(<ReportsPage />);

    // Page one, honestly labelled with the full total.
    expect(await screen.findByText(/Milk Producer 1$/)).toBeInTheDocument();
    expect(
      (await screen.findAllByText(/Showing 1–50 of 120/)).length,
    ).toBeGreaterThan(0);
    expect(supplierCalls[0].get("limit")).toBe("50");
    expect(supplierCalls[0].get("offset")).toBe("0");

    // Page two: supplier #51 — invisible before this milestone — exists.
    const nexts = screen.getAllByRole("button", { name: "Next" });
    await user.click(nexts[nexts.length - 1]);
    expect(await screen.findByText(/Milk Producer 51/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        supplierCalls.some((p) => p.get("offset") === "50"),
      ).toBe(true),
    );
    expect(
      (await screen.findAllByText(/Showing 51–100 of 120/)).length,
    ).toBeGreaterThan(0);
  });
});
