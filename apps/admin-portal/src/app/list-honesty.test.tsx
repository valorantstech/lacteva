/**
 * A list that ends is not the same as a list that is finished
 * (LACTEVA-ADMIN-007 + LACTEVA-ADMIN-010).
 *
 * Two failures of the same kind, at opposite ends of the same list.
 *
 * **When there is too much**, six screens fetched a fixed first page — a
 * hundred centres, fifty payments, ten receipts — and rendered exactly what
 * came back. For most dairies that is everything and the cap is invisible. For
 * the one dairy it is not, the list simply stops, and a centre that cannot be
 * selected is indistinguishable from a centre that was never created. The
 * platform returned an authoritative `total` on every one of those calls; it
 * was merely never read.
 *
 * **When there is nothing**, six more rendered a bare sentence in a table cell
 * — "No rate cards match." — which says what is absent and nothing about why,
 * or what the reader could do about it. An empty state that does not tell you
 * the next step is a dead end with better manners.
 *
 * These tests hold both ends: the cap is announced only when it bites, and the
 * empty state says why and what to do.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

import * as api from "@/lib/api";
import { CappedNotice } from "@/components/states";
import RateCardsPage from "@/app/rate-cards/page";
import ReportsPage from "@/app/reports/page";
import ResolvePage from "@/app/resolve/page";
import RolesPage from "@/app/admin/roles/page";
import SettlementsPage from "@/app/settlements/page";
import SyncPage from "@/app/sync/page";
import MatricesPage from "@/app/matrices/page";
import NotificationsPage from "@/app/notifications/page";
import ReceiptsPage from "@/app/receipts/page";

const page = (items: unknown[] = [], total = items.length) => ({
  items,
  total,
  limit: 50,
  offset: 0,
});

const centre = (i: number) => ({
  id: `c${i}`,
  branch_id: "b1",
  name: `Centre ${i}`,
  code: `C-${i}`,
  status: "active",
  timezone: "Asia/Kolkata",
});

/** A centres page whose `total` exceeds what it returned — the capped case. */
const cappedCentres = (shown: number, total: number) =>
  page(Array.from({ length: shown }, (_, i) => centre(i)), total);

/**
 * Mock by API function, not by URL.
 *
 * These pages call four or five endpoints with four or five different shapes,
 * and a blanket `fetch` stub feeds the wrong shape to whichever one it did not
 * anticipate — the page throws and renders nothing, and the test reports an
 * absent empty state that is really an absent page. This is the pattern
 * `notifications-page.test.tsx` already uses, for the same reason.
 */
function mockApi(overrides: Record<string, unknown> = {}) {
  const empties: Record<string, unknown> = {
    listCenters: page(),
    listRateCards: page(),
    listBranches: [],
    listNotifications: page(),
    listNotificationTemplates: [],
    getNotificationStats: { total: 0, by_status: {}, by_channel: {}, retryable: 0 },
    getTemplateRegistry: {
      total: 0,
      unmapped_whatsapp: 0,
      ready_whatsapp: 0,
      entries: [],
    },
    listSyncOperations: page(),
    // The real shape — an incomplete fixture here renders NOTHING and reads as
    // a missing empty state rather than a missing `devices` array.
    getSyncStats: {
      total: 0,
      by_status: {},
      by_kind: {},
      conflicts: 0,
      failed: 0,
      devices: [],
      last_sync_at: null,
    },
    listReceipts: page(),
    listMatrices: page(),
    listQualityDimensions: [],
    getCenterReport: page(),
    getSupplierReport: page(),
    getDailyReport: { items: [] },
    getPricingReport: { items: [] },
    getSettlementReport: { items: [] },
    listSettlements: page(),
    listSuppliers: page(),
    listPeople: [],
    listPermissions: {},
    listRoles: [],
  };
  for (const [name, value] of Object.entries({ ...empties, ...overrides })) {
    if (typeof (api as Record<string, unknown>)[name] === "function") {
      vi.spyOn(api as never, name as never).mockResolvedValue(value as never);
    }
  }
}

beforeEach(() => vi.restoreAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("the cap says so, and only when it bites", () => {
  it("stays silent when the list IS the whole list", () => {
    // The common case, and why this cannot simply always render: a dairy with
    // nine centres must not be told it has more.
    const { container } = render(
      <CappedNotice shown={9} total={9} noun="centres" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("counts nothing itself — the total is the platform's", () => {
    render(
      <CappedNotice shown={100} total={143} noun="centres" hint="Go and look." />,
    );
    // 143 is a number no arithmetic here produced.
    expect(screen.getByText(/Showing 100 of 143 centres\./)).toBeTruthy();
    expect(screen.getByText(/Go and look\./)).toBeTruthy();
  });

  it("announces itself politely, because a list can refill under the reader", () => {
    render(<CappedNotice shown={1} total={2} noun="payments" />);
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it.each([
    ["/reports", ReportsPage],
    ["/resolve", ResolvePage],
    ["/admin/roles", RolesPage],
    ["/settlements", SettlementsPage],
  ])("%s says when its centre list was cut short", async (_label, Page) => {
    mockApi({ listCenters: cappedCentres(100, 143) });
    render(<Page />);
    await waitFor(() =>
      expect(screen.getByText(/Showing 100 of 143 centres/)).toBeTruthy(),
    );
  });

  it.each([
    ["/reports", ReportsPage],
    ["/settlements", SettlementsPage],
  ])("%s stays quiet when every centre came back", async (_label, Page) => {
    mockApi({ listCenters: cappedCentres(3, 3) });
    render(<Page />);
    await waitFor(() => expect(screen.queryByText(/Showing 3 of 3/)).toBeNull());
  });
});

describe("an empty table says why, and what to do next", () => {
  it.each([
    ["rate cards", RateCardsPage, /A rate card is what turns fat and quantity into money/],
    ["notifications", NotificationsPage, /Messages appear here after the platform sends one/],
    ["sync", SyncPage, /A handset appears here the first time it sends captured work/],
    ["receipts", ReceiptsPage, /A receipt is generated when a payment completes/],
    ["matrices", MatricesPage, /A matrix holds the bands that price a product by quality/],
    ["reports", ReportsPage, /Widen the range, or clear the centre filter/],
  ])("%s explains itself when empty and loaded", async (_label, Page, expected) => {
    mockApi();
    render(<Page />);
    // The next step, not just the absence.
    await waitFor(() => expect(screen.getByText(expected)).toBeTruthy());
  });

  it("does not claim emptiness before the first fetch has answered", async () => {
    // A page that says "nothing here" while it is still asking is telling the
    // same lie the loading states in LACTEVA-ADMIN-001 removed.
    vi.spyOn(api, "listRateCards").mockImplementation(
      () => new Promise(() => {}) as never,
    );
    render(<RateCardsPage />);
    await new Promise((r) => setTimeout(r, 60));
    expect(screen.queryByText(/A rate card is what turns fat/)).toBeNull();
  });
});
