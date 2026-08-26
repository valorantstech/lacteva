/**
 * Rate-pending collections, in the portal (LACTEVA-BACKEND-001; D-3).
 *
 * A collection the platform could not price is not "unpriced" in the ordinary
 * sense — it is waiting on a rate card somebody has to publish, and until they
 * do, that farmer cannot be paid for milk the dairy already has. The list said
 * only "not priced", which reads like an absence rather than a job.
 *
 * What these tests defend:
 *
 *   1. the state is SAID, in words, with the status vocabulary — never left to
 *      an em-dash where an amount should be, and never colour alone;
 *   2. the action exists exactly where the problem is visible, and only when
 *      it can do something: a priced collection offers nothing to resolve;
 *   3. a refusal shows the PLATFORM's reason — "no published rate card covers
 *      this center, product, and date" is the sentence that tells an
 *      administrator what to go and do — and the badge stays Rate pending,
 *      because nothing was resolved.
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

/** The handset scenario: captured, completed, and never priced. */
const PENDING_TX = {
  id: "tx-9",
  session_id: "se-1",
  center_id: "c1",
  supplier_id: "s1",
  operator_id: "u1",
  state: "COMPLETED",
  milk_type: "cow",
  milk_type_custom: null,
  container_type: "can",
  container_identifier: "CAN-07",
  arrival_temperature_c: null,
  arrived_at: null,
  weight_unit: "kg",
  gross_weight: 42.5,
  tare_weight: 2.5,
  net_weight: 40,
  weight_source: "manual",
  fat: 4.2,
  snf: 8.5,
  clr: 27,
  density: null,
  quality_temperature_c: null,
  quality_remarks: "",
  quality_source: "manual",
  pricing_status: "pricing_unavailable",
  unit_price: null,
  gross_amount: null,
  currency: null,
  calculation_id: null,
  pricing_detail: "no published rate card covers this center, product, and date",
  rejected_reason: null,
  decided_by: "u1",
  decided_at: "2026-08-26T07:44:00+00:00",
  cancelled_reason: null,
  created_at: "2026-08-26T07:30:00+00:00",
  completed_at: "2026-08-26T07:45:00+00:00",
};

/** The same collection, after a card covering its date was published. */
const RESOLVED_TX = {
  ...PENDING_TX,
  pricing_status: "priced",
  unit_price: "45.0000",
  gross_amount: "1800.00",
  currency: "KES",
  calculation_id: "calc-9",
  pricing_detail: "LATE v1 band [4.0, 5.0)",
};

const CENTER = {
  id: "c1",
  branch_id: "b1",
  name: "Kilima Hill",
  code: "KH-C1",
  status: "active",
  timezone: "Africa/Nairobi",
};

function routeAll(overrides: Record<string, (url: string) => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    // Matched on the PATH, and by suffix: `.../tx-9` must not also swallow
    // `.../tx-9/events`, which an `includes` on the whole URL happily did.
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (path.endsWith(fragment)) return handler(url);
    }
    if (url.includes("/reprice") && init?.method === "POST") {
      return json(RESOLVED_TX);
    }
    if (path.endsWith("/v1/reports/collection/operational-status"))
      return json({ items: [] });
    if (path.endsWith("/v1/reports/collection/daily"))
      return json({ items: [], total: 0 });
    if (path.endsWith("/chain"))
      return json({
        transaction_id: "tx-9",
        settlement: null,
        payment: null,
        receipt: null,
      });
    if (path.endsWith("/v1/milk-transactions/tx-9/events")) return json([]);
    if (path.endsWith("/v1/milk-transactions/tx-9")) return json(PENDING_TX);
    if (path.endsWith("/v1/milk-transactions"))
      return json({ items: [PENDING_TX], total: 1, limit: 15, offset: 0 });
    if (path.endsWith("/v1/collection-centers/c1"))
      return json({
        center: CENTER,
        settings: {},
        operating_windows: [],
        calendar: [],
      });
    if (path.endsWith("/v1/collection-centers"))
      return json({ items: [CENTER], total: 1, limit: 100, offset: 0 });
    if (path.includes("/v1/suppliers/s1"))
      return json({
        supplier: {
          id: "s1",
          code: "S-88A723",
          status: "active",
          center_ids: ["c1"],
        },
        profile: { full_name: "Amina Njoroge", phone: "", village: "" },
      });
    if (path.endsWith("/v1/suppliers"))
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    if (path.endsWith("/v1/members")) return json([]);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** A FRESH promise per render: `use()` consumes it, and a module-level one
 *  reused across tests is a promise React has already settled elsewhere. */
const params = () => Promise.resolve({ id: "tx-9" });

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

/** The detail page reads its route params with `use()`, which SUSPENDS. With
 *  no boundary React renders nothing at all — no fetch, no DOM, and a
 *  "cannot find the button" that has nothing to do with the button. */
const renderDetail = async (ui: React.ReactElement) => {
  await act(async () => {
    render(<Suspense fallback={<span>loading route…</span>}>{ui}</Suspense>);
  });
};

describe("a rate-pending collection in the list", () => {
  it("says Rate pending in words, where the amount would be", async () => {
    routeAll();
    render(<TransactionsPage />);

    // Not an em-dash and not "not priced": the status vocabulary, so the
    // meaning survives without colour.
    expect(await screen.findByText("Rate pending")).toBeTruthy();
  });
});

describe("a rate-pending collection in detail", () => {
  it("offers Resolve price, and says why it is needed", async () => {
    routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);

    expect(
      await screen.findByRole("button", { name: "Resolve price" }),
    ).toBeTruthy();
    expect(
      screen.getByText(/No published rate card covered this collection/),
    ).toBeTruthy();
  });

  it("resolves through the platform and shows the amount it computed", async () => {
    const spy = routeAll();
    await renderDetail(<TransactionDetailPage params={params()} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Resolve price" }),
    );

    // The platform's own route — the portal never prices anything itself.
    await waitFor(() => {
      const posted = spy.mock.calls.find(
        ([u, i]) =>
          String(u).includes("/reprice") &&
          (i as RequestInit | undefined)?.method === "POST",
      );
      expect(posted).toBeTruthy();
      expect(String(posted![0])).toContain("/v1/milk-transactions/tx-9/reprice");
    });

    // And the resulting amount is the platform's exact decimal string.
    await waitFor(() => expect(screen.getAllByText(/1,?800\.00/).length).toBeGreaterThan(0));
    // The offer is gone, because there is nothing left to resolve.
    expect(screen.queryByRole("button", { name: "Resolve price" })).toBeNull();
  });

  it("shows the platform's reason on refusal, and stays Rate pending", async () => {
    routeAll({
      "/reprice": () =>
        json(
          {
            title: "conflict",
            status: 409,
            detail: "The request conflicts with the current state.",
            extra: "no published rate card covers this center, product, and date",
          },
          409,
        ),
    });
    await renderDetail(<TransactionDetailPage params={params()} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Resolve price" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(
          "no published rate card covers this center, product, and date",
        ),
      ).toBeTruthy(),
    );
    // Nothing was resolved, so the offer and the state both remain.
    expect(screen.getByRole("button", { name: "Resolve price" })).toBeTruthy();
    expect(screen.getAllByText("Rate pending").length).toBeGreaterThan(0);
  });

  it("offers nothing to resolve on a collection that is already priced", async () => {
    routeAll({ "/v1/milk-transactions/tx-9": () => json(RESOLVED_TX) });
    await renderDetail(<TransactionDetailPage params={params()} />);

    // The amount appears in more than one place on a priced collection (the
    // figure and the money trail); one is enough to know it rendered.
    await waitFor(() =>
      expect(screen.getAllByText(/1,?800\.00/).length).toBeGreaterThan(0),
    );
    expect(screen.queryByRole("button", { name: "Resolve price" })).toBeNull();
    expect(screen.queryByText("Rate pending")).toBeNull();
  });
});
