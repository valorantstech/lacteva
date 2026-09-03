/**
 * The milk day book, as a page (WO-56 · BR-0030).
 *
 * What is defended here is the honesty of a ledger, not its layout:
 *
 *   the remainder is the platform's arithmetic, negative included;
 *   a cancellation asks for a reason before it can be sent;
 *   the sales line says it is not subtracted; and
 *   the controls are ABSENT, not disabled, without the permission.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/day-book",
}));

import DayBookPage from "@/app/day-book/page";
import { isCompleteDate } from "@/lib/complete-date";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const BOOK = {
  business_date: "2026-09-01",
  center_id: "c1",
  center_name: "Kilima Hill",
  rows: [
    {
      milk_type: "cow",
      collected_kg: 520.5,
      dispatched_kg: 400,
      remainder_kg: 120.5,
      collections: 31,
      dispatches: 1,
    },
    {
      milk_type: "buffalo",
      collected_kg: 180,
      dispatched_kg: 200,
      remainder_kg: -20,
      collections: 9,
      dispatches: 1,
    },
  ],
  total_collected_kg: 700.5,
  total_dispatched_kg: 600,
  total_remainder_kg: 100.5,
  quantity_unit: "kg",
  sales: {
    deliveries: 12,
    quantity: "48.000",
    quantity_unit: "L",
    attributable_to_centre: false,
    attributable_to_milk_type: false,
  },
};

const DISPATCH = {
  id: "d1",
  center_id: "c1",
  business_date: "2026-09-01",
  milk_type: "cow",
  quantity: "400.000",
  quantity_unit: "kg",
  destination: "Anand Chilling Plant",
  reference: "GP-4471",
  notes: "",
  status: "recorded",
  recorded_by: "u1",
  created_at: "2026-09-01T09:00:00+00:00",
  cancelled_by: null,
  cancelled_at: null,
  cancel_reason: "",
};

function routeAll(
  overrides: Record<string, () => Response> = {},
  { permissions = ["*"] }: { permissions?: string[] } = {},
) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/api/auth/session"))
      return json({
        authenticated: true,
        acting_tenant_id: "org-1",
        tenant_id: "org-1",
        permissions,
        user: { id: "u1", email: "manager@kilima.example", full_name: "Manager" },
      });
    if (url.includes("/reports/day-book")) return json(BOOK);
    if (url.includes("/v1/dispatches") && init?.method === "POST")
      return json(DISPATCH, 201);
    if (url.includes("/v1/dispatches"))
      return json({ items: [DISPATCH], total: 1, limit: 100, offset: 0 });
    if (url.includes("/collection-centers"))
      return json({
        items: [
          {
            id: "c1",
            branch_id: "b1",
            name: "Kilima Hill",
            code: "KH-C1",
            status: "active",
            timezone: "Africa/Nairobi",
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("the milk day book", () => {
  it("prints the platform's arithmetic, including a negative remainder", async () => {
    // A centre that dispatched more buffalo than it collected has recorded
    // something wrong. Showing 0 would hide exactly that.
    routeAll();
    render(<DayBookPage />);

    expect(await screen.findByText("520.5 kg")).toBeInTheDocument();
    // WO-68 rider: one decimal, as a dairy says it.
    expect(screen.getByText("-20.0 kg")).toBeInTheDocument();
    expect(screen.getAllByText("100.5 kg").length).toBeGreaterThan(0);
  });

  it("says the sales figure is not subtracted, and why", async () => {
    routeAll();
    render(<DayBookPage />);
    const note = await screen.findByText(/Sold today/);
    expect(note).toHaveTextContent(/not attributed to a centre/);
    expect(note).toHaveTextContent(/or to a milk type/);
    expect(note).toHaveTextContent(/NOT subtracted/);
  });

  it("records a dispatch through the platform, in kilograms", async () => {
    const spy = routeAll();
    render(<DayBookPage />);
    await screen.findByText("520.5 kg");

    await userEvent.selectOptions(screen.getByLabelText("Centre", { selector: "#dispatch-centre" }), "c1");
    await userEvent.selectOptions(screen.getByLabelText("Milk type"), "buffalo");
    await userEvent.type(screen.getByLabelText("Quantity (kg)"), "120.500");
    await userEvent.type(screen.getByLabelText("Destination"), "Anand Chilling Plant");
    await userEvent.click(screen.getByRole("button", { name: /record dispatch/i }));

    await waitFor(() => {
      const post = spy.mock.calls.find(
        ([u, init]) =>
          String(u).includes("/v1/dispatches") &&
          (init as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post?.[1] as RequestInit).body));
      expect(body).toMatchObject({
        center_id: "c1",
        milk_type: "buffalo",
        quantity: "120.500",
        destination: "Anand Chilling Plant",
      });
    });
  });

  it("asks for a reason before a dispatch can be cancelled", async () => {
    const spy = routeAll();
    render(<DayBookPage />);
    await screen.findByText("520.5 kg");

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    const reason = await screen.findByLabelText(/why is this dispatch being cancelled/i);
    // Nothing has been sent yet: the button opens a question, not a request.
    expect(
      spy.mock.calls.filter(([u]) => String(u).includes("/cancel")),
    ).toHaveLength(0);

    await userEvent.type(reason, "tanker turned back at the gate");
    await userEvent.click(screen.getByRole("button", { name: /confirm cancellation/i }));

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) => String(u).includes("/cancel"));
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
        reason: "tanker turned back at the gate",
      });
    });
  });

  it("offers no dispatch controls at all without the permission", async () => {
    // Absent, not disabled: a greyed-out button tells the person at the
    // counter that the capability exists and they are not trusted with it.
    routeAll({}, { permissions: ["operations.dispatch.read", "reporting.read"] });
    render(<DayBookPage />);
    await screen.findByText("520.5 kg");

    expect(screen.queryByRole("button", { name: /record dispatch/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    for (const button of screen.getAllByRole("button")) {
      expect(button).not.toBeDisabled();
    }
  });

  it("does not read a failed load as a day with no milk", async () => {
    routeAll({ "/reports/day-book": () => json({ detail: "boom" }, 500) });
    render(<DayBookPage />);
    // QA-004: `findByRole("alert")` asks for THE alert, and this page has
    // three regions that fail independently. Find the one that SAYS it.
    await waitFor(() =>
      expect(
        screen
          .getAllByRole("alert")
          .some((el) => /not the same as a day with nothing in it/i.test(el.textContent ?? "")),
      ).toBe(true),
    );
    expect(screen.queryByText(/nothing recorded for this day/i)).not.toBeInTheDocument();
  });
});

describe("typing a date into the day book (WO-68)", () => {
  it("sends only a complete date and keeps the previous view meanwhile", async () => {
    // A `<input type="date">` emits intermediate values while someone types;
    // `0008-30-2026` was captured from a real browser. The page used to send
    // each one, earn a 422 whose `detail` is an array, and die rendering it.
    const spy = routeAll();
    render(<DayBookPage />);
    await waitFor(() => expect(screen.getAllByText(/700\.5/).length).toBeGreaterThan(0));
    const bookCalls = () =>
      spy.mock.calls.filter(([url]) => String(url).includes("/reports/day-book"));
    const before = bookCalls().length;
    expect(before).toBeGreaterThan(0);

    const input = screen.getByLabelText("Business date") as HTMLInputElement;
    // What a browser hands over mid-typing, and what jsdom sanitises it to.
    for (const partial of ["0008-30-2026", "2026-13-01", "2026-02-31", "", "2026-0"]) {
      fireEvent.change(input, { target: { value: partial } });
      await new Promise((r) => setTimeout(r, 150));
    }
    expect(bookCalls().length).toBe(before);
    for (const [url] of bookCalls()) {
      expect(String(url)).not.toContain("0008-30-2026");
      expect(String(url)).toContain("business_date=20");
    }
    // The ledger is still showing the last complete day.
    expect(screen.getAllByText(/700\.5/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/couldn't load|Unprocessable/i)).not.toBeInTheDocument();

    // A complete date is sent, once.
    fireEvent.change(input, { target: { value: "2026-09-02" } });
    await waitFor(() => expect(bookCalls().length).toBe(before + 1));
    expect(String(bookCalls().at(-1)?.[0])).toContain("business_date=2026-09-02");
  });

  it("knows which dates are complete", () => {
    expect(isCompleteDate("2026-09-02")).toBe(true);
    expect(isCompleteDate("2024-02-29")).toBe(true);
    for (const bad of ["0008-30-2026", "2026-13-01", "2026-02-31", "2026-0", "", "2026-9-2"]) {
      expect(isCompleteDate(bad), bad).toBe(false);
    }
  });
});
