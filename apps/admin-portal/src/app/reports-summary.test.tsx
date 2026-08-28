/**
 * A summary card must not take the page down with it (WO-33 portal rider).
 *
 * `/reports` reads a daily summary and renders four figures from it. The page
 * guarded the SUMMARY — `daily && (...)` — but not the one field it then
 * reached two levels into:
 *
 *     Object.entries(daily.payable_by_currency)
 *
 * `Object.entries(undefined)` does not return nothing. It throws "Cannot
 * convert undefined or null to object" during render, so it surfaces as an
 * UNHANDLED error rather than a failing assertion. The whole portal suite
 * exited 1 on `main` because of it while all 533 of its tests reported
 * passing — the worst shape a defect can take: a red gate that names no test
 * and blames no file.
 *
 * The trigger is already in the repository. `list-honesty.test.tsx` mocks
 * `getDailyReport: { items: [] }` — truthy, and without that field — so four
 * of its cases have been walking into this the whole time.
 *
 * The API type declares the field required, so this is not a payload today's
 * backend sends. But "the type says so" is precisely the reasoning that put
 * an unguarded reach into a render path, and a page whose failure mode is a
 * blank screen has to survive a field it did not get.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

import * as api from "@/lib/api";
import ReportsPage from "@/app/reports/page";

const page = (items: unknown[] = [], total = items.length) => ({
  items,
  total,
  limit: 50,
  offset: 0,
});

/** Everything `/reports` asks for; `getDailyReport` is the one under test. */
function mockReports(daily: unknown) {
  const responses: Record<string, unknown> = {
    listCenters: page(),
    getCenterReport: page(),
    getSupplierReport: page(),
    getPricingReport: { items: [] },
    getSettlementReport: { items: [] },
    getDailyReport: daily,
  };
  for (const [name, value] of Object.entries(responses)) {
    if (typeof (api as Record<string, unknown>)[name] === "function") {
      vi.spyOn(api as never, name as never).mockResolvedValue(value as never);
    }
  }
}

/** A summary with every figure the page reads, minus the one being withheld. */
const summary = (extra: Record<string, unknown> = {}) => ({
  total_net_weight_kg: 1184.5,
  transactions: 12,
  accepted: 11,
  rejected: 1,
  weighted_avg_fat: "4.10",
  weighted_avg_snf: "8.50",
  unpriced_accepted: 0,
  in_progress: 0,
  ...extra,
});

/**
 * The summary card with this label.
 *
 * `/reports` prints "Payable" three times — once as a summary card label and
 * twice as a table column header — so `getByText("Payable")` throws "Found
 * multiple elements", which is QA-003's failure wearing a different hat. The
 * card's label is a `<p>`; the others are `<th>`.
 */
function summaryCard(label: string): HTMLElement {
  const found = screen
    .getAllByText(label)
    .find((el) => el.tagName === "P");
  if (!found?.parentElement) {
    throw new Error(`no summary card labelled ${label}`);
  }
  return found.parentElement;
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("the daily summary survives a field it did not get", () => {
  it("renders the summary when payable_by_currency is missing", async () => {
    mockReports(summary());
    render(<ReportsPage />);
    // Before the fix this threw while rendering the summary block, so the
    // block — and everything the page draws after it — never existed.
    await waitFor(() => expect(summaryCard("Payable")).toBeTruthy());
    expect(screen.getByText("1184.5 kg")).toBeTruthy();
    expect(screen.getByText("12 (11✓ / 1✗)")).toBeTruthy();
  });

  it("reads as absent, never as zero, when the platform sent no figure", async () => {
    // "0" here would be a claim that the dairy owes nobody anything, which is
    // a different statement from "the platform did not say".
    mockReports(summary());
    render(<ReportsPage />);
    await waitFor(() => expect(summaryCard("Payable")).toBeTruthy());
    expect(summaryCard("Payable").textContent).toContain("—");
    expect(summaryCard("Payable").textContent).not.toContain("0");
  });

  it("survives the exact fixture the rest of the suite already ships", async () => {
    // `list-honesty.test.tsx`'s own `getDailyReport: { items: [] }`.
    mockReports({ items: [] });
    render(<ReportsPage />);
    await waitFor(() => expect(summaryCard("Payable")).toBeTruthy());
  });

  it("still prints the currencies when they are there", async () => {
    mockReports(summary({ payable_by_currency: { INR: "13860.00" } }));
    render(<ReportsPage />);
    await waitFor(() =>
      expect(screen.getByText(/13,860\.00 INR/)).toBeTruthy(),
    );
  });
});
