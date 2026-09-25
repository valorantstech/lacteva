/**
 * The month sheet (WO-84): the shop's register, computed.
 *
 *  * one row per (customer, product), a cell per day — a BLANK cell is
 *    blank, not "0" and not "—";
 *  * today's column is marked, from the platform's business date;
 *  * the totals block is in their sheet's order and the CSV link carries the
 *    same month and filters;
 *  * a blank cell opens an editor that RECORDS through `/v1/deliveries` with
 *    the row's product; a billed cell is read-only and says why.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/deliveries/month",
  useSearchParams: () => new URLSearchParams(),
}));

import MonthSheetPage from "@/app/deliveries/month/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const cell = (quantity: string | null, extra: Partial<{ delivery_id: string; status: string; billed: boolean }> = {}) => ({
  quantity,
  delivery_id: extra.delivery_id ?? (quantity === null ? null : "d-x"),
  status: extra.status ?? (quantity === null ? null : "delivered"),
  billed: extra.billed ?? false,
});

const DAYS = 31;
const days = (fill: (i: number) => ReturnType<typeof cell> | null) =>
  Array.from({ length: DAYS }, (_, i) => fill(i));

const SHEET = {
  year: 2026,
  month: 8,
  date_from: "2026-08-01",
  date_to: "2026-08-31",
  today: "2026-08-12",
  currency: "INR",
  quantity_unit: "L",
  product: null,
  route_id: null,
  rows: [
    {
      customer_id: "cu-1",
      code: "H-001",
      name: "Tower 1-2006",
      product: "COW-MILK",
      unit_price: "74.0000",
      quantity_unit: "L",
      days: days((i) =>
        i === 2
          ? null
          : i === 3
            ? cell(null, { delivery_id: "d-s", status: "scheduled" })
            : i === 0
              ? cell("1.000", { delivery_id: "d-billed", billed: true })
              : i === 5
                ? { ...cell("1.000", { delivery_id: "d-70" }), price_source: "override" as const, unit_price: "70.0000" }
                : cell("1.000"),
      ),
      total_quantity: "29.000",
      milk_amount: "2146.00",
      items_amount: "0.00",
      previous_balance: "0.00",
      total_due: "2146.00",
      received: "2000.00",
      method: "UPI",
      received_on: "2026-08-10",
    },
    {
      customer_id: "cu-2",
      code: "H-002",
      name: "A-1607",
      product: "BUFFALO-MILK",
      unit_price: "56.0000",
      quantity_unit: "L",
      days: days(() => cell("0.750")),
      total_quantity: "23.250",
      milk_amount: "1302.00",
      items_amount: "160.00",
      previous_balance: "244.00",
      total_due: "1706.00",
      received: "0.00",
      method: null,
      received_on: null,
    },
  ],
  day_totals: Array.from({ length: DAYS }, (_, i) => (i === 2 ? "0.750" : "1.750")),
  totals: {
    quantity: "52.250",
    milk_amount: "3448.00",
    items_amount: "160.00",
    previous_balance: "244.00",
    total_due: "3852.00",
    received: "2000.00",
  },
};

function stub() {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.includes("/api/auth/session"))
      return json({
        authenticated: true,
        organization: { timezone: "Asia/Kolkata" },
        permissions: ["sales.delivery.read", "sales.delivery.record"],
      });
    if (path.includes("/v1/auth/me"))
      return json({
        organization: { timezone: "Asia/Kolkata" },
        permissions: ["sales.delivery.read", "sales.delivery.record"],
      });
    if (path.includes("/v1/products")) return json({ items: [{ code: "COW-MILK", name: "Cow milk" }], total: 1 });
    if (path.includes("/v1/routes")) return json([]);
    if (path.includes("/v1/deliveries/month")) return json(SHEET);
    if (path.endsWith("/v1/deliveries") && init?.method === "POST")
      return json({ id: "d-new", status: "delivered" }, 201);
    if (path.includes("/amend") && init?.method === "POST") return json({ id: "d-x" });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("the month sheet", () => {
  it("draws one row per household and product, blank where nothing was delivered, and marks today", async () => {
    const spy = stub();
    await act(async () => {
      render(<MonthSheetPage />);
    });
    const table = await screen.findByRole("table", { name: "Month sheet" });
    const tower = within(table).getByTestId("month-row-H-001-COW-MILK");
    // Day 3 (index 2): nothing at all. Day 4: scheduled — also blank, but the cell knows.
    const d3 = within(tower).getByRole("button", { name: "Tower 1-2006 COW-MILK day 3" });
    expect(d3.textContent).toBe("");
    const d4 = within(tower).getByRole("button", { name: "Tower 1-2006 COW-MILK day 4" });
    expect(d4.textContent).toBe("");
    expect(d4.closest("td")?.getAttribute("data-kind")).toBe("scheduled");
    const d5 = within(tower).getByRole("button", { name: "Tower 1-2006 COW-MILK day 5: 1" });
    expect(d5.textContent).toBe("1");
    // "1.000" reads as 1, "0.750" as 0.75 — the way their sheet writes it.
    expect(within(within(table).getByTestId("month-row-H-002-BUFFALO-MILK")).getAllByText("0.75").length).toBe(DAYS);
    // Today's column, from the platform's business date.
    const todayHeader = within(table).getAllByRole("columnheader").find((th) => th.getAttribute("data-today") === "true");
    expect(todayHeader?.textContent).toBe("12");
    // The totals block, in their order, and the footer.
    const a1607 = within(table).getByTestId("month-row-H-002-BUFFALO-MILK");
    const cells = within(a1607).getAllByRole("cell").map((c) => c.textContent);
    const tail = cells.slice(-7);
    expect(tail[0]).toBe("23.25");
    expect(tail[1]).toContain("160");
    expect(tail[2]).toContain("244");
    expect(tail[3]).toContain("1,706");
    expect(tail[4]).toBe("");
    const footer = within(table).getByTestId("month-totals");
    expect(footer.textContent).toContain("3,852");
    // The CSV link carries the same month and filters the sheet was asked for
    // (the default month is the business date's, which this stub cannot pin).
    const asked = spy.mock.calls
      .map((c) => String(c[0]))
      .find((u) => u.includes("/v1/deliveries/month?"))!;
    const query = asked.split("?")[1];
    expect(query).toMatch(/^year=\d{4}&month=\d{1,2}$/);
    expect(screen.getByTestId("month-sheet-csv").getAttribute("href")).toBe(
      `/api/proxy/v1/deliveries/month.csv?${query}`,
    );
  });

  it("a blank cell records through the platform with the row's product; a billed cell is read-only", async () => {
    const spy = stub();
    const user = userEvent.setup();
    await act(async () => {
      render(<MonthSheetPage />);
    });
    const table = await screen.findByRole("table", { name: "Month sheet" });
    const tower = within(table).getByTestId("month-row-H-001-COW-MILK");
    await user.click(within(tower).getByRole("button", { name: "Tower 1-2006 COW-MILK day 3" }));
    const editor = await screen.findByTestId("month-cell-editor");
    expect(editor.textContent).toContain("2026-08-03");
    await user.type(within(editor).getByLabelText(/Quantity/), "1.5");
    await user.click(within(editor).getByRole("button", { name: "Record" }));
    await waitFor(() =>
      expect(
        spy.mock.calls.some(
          (c) => String(c[0]).endsWith("/v1/deliveries") && (c[1] as RequestInit)?.method === "POST",
        ),
      ).toBe(true),
    );
    const post = spy.mock.calls.find(
      (c) => String(c[0]).endsWith("/v1/deliveries") && (c[1] as RequestInit)?.method === "POST",
    )!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({
      customer_id: "cu-1",
      delivery_date: "2026-08-03",
      product: "COW-MILK",
      status: "delivered",
      quantity: "1.5",
    });

    // WO-89: a rate typed for the day travels with the record; the plan's is the placeholder.
    await user.click(within(tower).getByRole("button", { name: "Tower 1-2006 COW-MILK day 5: 1" }));
    const priced = await screen.findByTestId("month-cell-editor");
    const rateField = within(priced).getByLabelText(/Rate for this day/) as HTMLInputElement;
    expect(rateField.placeholder).toBe("plan: 74");
    await user.type(rateField, "70");
    await user.click(within(priced).getByRole("button", { name: "Correct" }));
    await waitFor(() =>
      expect(spy.mock.calls.some((c) => String(c[0]).endsWith("/v1/deliveries/d-x/amend"))).toBe(true),
    );
    const amend = spy.mock.calls.find((c) => String(c[0]).endsWith("/v1/deliveries/d-x/amend"))!;
    expect(JSON.parse(String((amend[1] as RequestInit).body))).toMatchObject({ unit_price: "70" });
    // Day 6 was priced away from the plan: marked on the cell, prefilled in the editor.
    const d6 = within(tower).getByRole("button", { name: /day 6: 1 \(rate agreed for this day\)/ });
    expect(d6.closest("td")?.getAttribute("data-override")).toBe("true");
    await user.click(d6);
    expect((within(await screen.findByTestId("month-cell-editor")).getByLabelText(/Rate for this day/) as HTMLInputElement).value).toBe("70");

    // Day 1 is on an issued invoice: no form, and the sentence says why.
    await user.click(within(tower).getByRole("button", { name: "Tower 1-2006 COW-MILK day 1: 1" }));
    const locked = await screen.findByTestId("month-cell-editor");
    expect(locked.textContent).toMatch(/issued invoice is immutable/);
    expect(within(locked).queryByRole("button", { name: /Record|Correct/ })).toBeNull();
  });
});
