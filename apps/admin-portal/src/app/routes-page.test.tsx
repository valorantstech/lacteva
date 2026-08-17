import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import RoutesPage from "./routes/page";

/**
 * Routes and runs (DEMO-034).
 *
 * The properties worth asserting on a screen are the two the domain cares
 * about: that the page shows the DELIVERY domain's own outcome rather than a
 * second copy, and that it never displays a figure of money — because a route
 * is an operational record and a page that showed an amount would be claiming
 * otherwise.
 */

const ROUTE = {
  id: "route-1",
  code: "R-01",
  name: "Kilima morning round",
  center_id: null,
  active: true,
  notes: "",
  stop_count: 3,
};

const RUN = {
  id: "run-1",
  route_id: "route-1",
  route_code: "R-01",
  route_name: "Kilima morning round",
  business_date: "2026-08-17",
  slot: "morning",
  vehicle_id: null,
  vehicle_registration: null,
  driver_id: null,
  driver_name: null,
  status: "planned" as const,
  notes: "",
  started_at: null,
  finished_at: null,
  stops: [],
};

function stubApi(overrides: { runs?: unknown[] } = {}) {
  vi.spyOn(api, "listRoutes").mockResolvedValue([ROUTE] as never);
  vi.spyOn(api, "listVehicles").mockResolvedValue([
    { id: "v-1", registration: "KDA 123X", label: "Blue van", center_id: null, active: true },
  ] as never);
  vi.spyOn(api, "listDrivers").mockResolvedValue([
    {
      id: "d-1",
      code: "DRV-1",
      full_name: "Joseph Mwangi",
      phone: "+254733000111",
      user_id: null,
      center_id: null,
      active: true,
    },
  ] as never);
  vi.spyOn(api, "listDeliveryRuns").mockResolvedValue(
    (overrides.runs ?? [RUN]) as never,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("routes and runs", () => {
  it("lists the routes a dairy has, with how many stops each visits", async () => {
    stubApi();
    render(<RoutesPage />);

    expect(await screen.findByText("Kilima morning round")).toBeInTheDocument();
    expect(screen.getByText("R-01")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("asks the PLATFORM which day it is, and never sends a date", async () => {
    // DEMO-013: a browser in another timezone must not decide which day a
    // dairy is having, so the listing call carries no date at all.
    stubApi();
    const spy = vi.spyOn(api, "listDeliveryRuns");
    render(<RoutesPage />);

    await screen.findByText("Kilima morning round");
    expect(spy).toHaveBeenCalledWith();
  });

  it("offers only the transitions the run is actually allowed", async () => {
    stubApi();
    render(<RoutesPage />);

    await screen.findByText("Today's runs");
    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    // A planned run cannot be completed, so the button is not offered.
    expect(screen.queryByRole("button", { name: "Complete" })).toBeNull();
  });

  it("shows a completed run as terminal, with nothing left to press", async () => {
    stubApi({ runs: [{ ...RUN, status: "completed" }] });
    render(<RoutesPage />);

    // Wait for the RUN, not for the heading. The heading is static, so
    // asserting after it passes before the load resolves — which is how the
    // first draft of this test passed for the wrong reason: with an empty list
    // there are no buttons either way, and the mutation that offers "Start" on
    // a completed run survived it.
    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(screen.queryByText("No run planned for today yet.")).toBeNull();

    for (const label of ["Start", "Complete", "Cancel"]) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
  });

  it("shows the platform's refusal verbatim rather than a generic message", async () => {
    // "a run needs both a driver and a vehicle before it can start" is the
    // sentence an operator has to act on.
    stubApi();
    vi.spyOn(api, "setDeliveryRunStatus").mockRejectedValue(
      new api.ApiError(
        409,
        "a run needs both a driver and a vehicle before it can start",
      ),
    );
    render(<RoutesPage />);

    await screen.findByText("Today's runs");
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(
      await screen.findByText(
        "a run needs both a driver and a vehicle before it can start",
      ),
    ).toBeInTheDocument();
  });

  it("assigns a vehicle by sending only what changed", async () => {
    stubApi();
    const spy = vi
      .spyOn(api, "assignDeliveryRun")
      .mockResolvedValue({ ...RUN, vehicle_id: "v-1" } as never);
    render(<RoutesPage />);

    await screen.findByText("Today's runs");
    fireEvent.change(screen.getByLabelText("Vehicle"), {
      target: { value: "v-1" },
    });

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("run-1", { vehicle_id: "v-1" }),
    );
  });

  it("shows no money anywhere, because a route is not a financial document", async () => {
    stubApi();
    render(<RoutesPage />);

    await screen.findByText("Kilima morning round");
    const text = document.body.textContent ?? "";
    for (const symbol of ["KES", "INR", "₹", "$", "amount", "invoice", "balance"]) {
      expect(text.toLowerCase()).not.toContain(symbol.toLowerCase());
    }
  });
});
