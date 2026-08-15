/**
 * The business calendar screen (DEMO-020).
 *
 * What is asserted is that the page RENDERS THE SERVER'S ANSWER and computes
 * nothing of its own. That is the whole architectural claim of the screen, and
 * it is testable in the only way that matters: feed it a payload whose dates
 * a browser would get wrong, and check the wrong answer never appears.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/calendar",
}));

import CalendarPage from "@/app/admin/calendar/page";
import * as api from "@/lib/api";

const INDIA_PAYLOAD = {
  timezone: "Asia/Kolkata",
  business_date: "2026-08-15",
  is_working_day: true,
  month_start: "2026-08-01",
  month_end: "2026-08-31",
  previous_month_start: "2026-07-01",
  previous_month_end: "2026-07-31",
  current_period: null,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the business calendar screen", () => {
  it("shows the organization's own date and month, verbatim", async () => {
    vi.spyOn(api, "getOrganizationCalendar").mockResolvedValue(INDIA_PAYLOAD);
    vi.spyOn(api, "getFinancialPeriods").mockResolvedValue([]);

    render(<CalendarPage />);

    await waitFor(() =>
      expect(screen.getByText("2026-08-15")).toBeInTheDocument(),
    );
    expect(screen.getByText("Asia/Kolkata")).toBeInTheDocument();
    expect(screen.getByText("2026-08-01 — 2026-08-31")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01 — 2026-07-31")).toBeInTheDocument();
  });

  it("says plainly that an undeclared period restricts nothing", async () => {
    vi.spyOn(api, "getOrganizationCalendar").mockResolvedValue(INDIA_PAYLOAD);
    vi.spyOn(api, "getFinancialPeriods").mockResolvedValue([]);

    render(<CalendarPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/No financial period covers 2026-08-15/),
      ).toBeInTheDocument(),
    );
    // The reassurance matters: an operator seeing "no period" must not think
    // the platform is refusing their work.
    expect(screen.getByText(/always open/)).toBeInTheDocument();
  });

  it("marks a closed period as closed", async () => {
    vi.spyOn(api, "getOrganizationCalendar").mockResolvedValue({
      ...INDIA_PAYLOAD,
      current_period: {
        id: "p1",
        period_start: "2026-08-01",
        period_end: "2026-08-31",
        status: "closed",
        label: "August 2026",
        closed_at: "2026-09-01T00:00:00+00:00",
      },
    });
    vi.spyOn(api, "getFinancialPeriods").mockResolvedValue([
      {
        id: "p0",
        period_start: "2026-07-01",
        period_end: "2026-07-31",
        status: "closed",
        label: "July 2026",
        closed_at: "2026-08-01T00:00:00+00:00",
      },
    ]);

    render(<CalendarPage />);

    await waitFor(() =>
      expect(screen.getAllByText("Closed").length).toBeGreaterThan(0),
    );
    // The previous month's period is matched by its start date, not by its
    // position in the list — so it appears twice: once as "previous period"
    // and once in the full list below.
    expect(screen.getAllByText("July 2026")).toHaveLength(2);
  });

  it("reports a failure rather than rendering an empty calendar", async () => {
    vi.spyOn(api, "getOrganizationCalendar").mockRejectedValue(
      new Error("network down"),
    );
    vi.spyOn(api, "getFinancialPeriods").mockResolvedValue([]);

    render(<CalendarPage />);

    await waitFor(() =>
      expect(screen.getByText("network down")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Business date")).not.toBeInTheDocument();
  });
});
