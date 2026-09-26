import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

function stubApi(
  overrides: { runs?: unknown[]; members?: unknown[]; userNames?: Record<string, string> } = {},
) {
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
  // WO-108: the page also asks who holds the Delivery boy role, and names them.
  vi.spyOn(api, "listMembers").mockResolvedValue((overrides.members ?? []) as never);
  vi.spyOn(api, "getUser").mockImplementation(async (id: string) =>
    ({ id, email: `${id}@patel.example`, full_name: overrides.userNames?.[id] ?? id, locale: "en", is_active: true }) as never,
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
    // WO-108: the stop count is the way into the stops editor.
    expect(
      screen.getByRole("button", { name: "Edit the stops of Kilima morning round" }),
    ).toHaveTextContent("3 stops");
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

    // Wait for the RUN, not the heading: the heading is static, so asserting
    // after it races the load and fails only when the machine is busy.
    expect(await screen.findByRole("button", { name: "Start" })).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: "Start" }));

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

    fireEvent.change(await screen.findByLabelText("Vehicle"), {
      target: { value: "v-1" },
    });

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("run-1", { vehicle_id: "v-1" }),
    );
  });

  it("generates the round and reports what the delivery domain did", async () => {
    // DEMO-035. The counts are the delivery domain's, passed through — this
    // screen computes nothing.
    stubApi();
    const spy = vi.spyOn(api, "generateDeliveryRun").mockResolvedValue({
      run_id: "run-1",
      route_code: "R-01",
      business_date: "2026-08-17",
      slot: "morning",
      stops: 3,
      due: 2,
      created: 2,
      already_present: 0,
      not_due: 1,
      inactive_customers: 0,
      skipped_holiday: 0,
    } as never);
    render(<RoutesPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate round" }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("run-1"));
    expect(
      await screen.findByText(/2 of 3 stops generated/),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 not due today/)).toBeInTheDocument();
  });

  it("says a second generation found the round already there", async () => {
    // `created: 0` is idempotency holding, not a failure, so the sentence has
    // to say which it is rather than showing a bare zero.
    stubApi();
    vi.spyOn(api, "generateDeliveryRun").mockResolvedValue({
      run_id: "run-1",
      route_code: "R-01",
      business_date: "2026-08-17",
      slot: "morning",
      stops: 3,
      due: 3,
      created: 0,
      already_present: 3,
      not_due: 0,
      inactive_customers: 0,
      skipped_holiday: 0,
    } as never);
    render(<RoutesPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate round" }));

    expect(await screen.findByText(/3 already there/)).toBeInTheDocument();
  });

  it("does not offer to generate into a closed round", async () => {
    stubApi({ runs: [{ ...RUN, status: "completed" }] });
    render(<RoutesPage />);

    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate round" })).toBeNull();
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

// --- WO-82 §3: today's round, without the owner ------------------------------

describe("a route that plans its own morning (WO-82)", () => {
  it("names a default driver by sending only that, and the switch waits for it", async () => {
    stubApi();
    // WO-108: the default is chosen from LINKED delivery boys — a profile
    // with a login is one whose phone will show the round.
    vi.spyOn(api, "listDrivers").mockResolvedValue([
      { id: "d-1", code: "DRV-1", full_name: "Joseph Mwangi", phone: "", user_id: "u-1", center_id: null, active: true },
    ] as never);
    const spy = vi
      .spyOn(api, "updateRoute")
      .mockResolvedValue({ ...ROUTE, default_driver_id: "d-1" } as never);
    render(<RoutesPage />);
    const toggle = (await screen.findByLabelText("Plan R-01 every morning")) as HTMLInputElement;
    expect(toggle.disabled).toBe(true);
    expect(screen.getByText("needs a default driver")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Default delivery boy for R-01"), {
      target: { value: "d-1" },
    });
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("route-1", { default_driver_id: "d-1" }),
    );
    expect(
      screen.getByText(/the round will exist every morning without anyone creating it/i),
    ).toBeInTheDocument();
  });

  it("turns auto-plan on once a driver is named, and withdraws a default explicitly", async () => {
    vi.spyOn(api, "listRoutes").mockResolvedValue([
      { ...ROUTE, default_driver_id: "d-1", auto_plan: false },
    ] as never);
    stubApi();
    vi.spyOn(api, "listRoutes").mockResolvedValue([
      { ...ROUTE, default_driver_id: "d-1", auto_plan: false },
    ] as never);
    const spy = vi
      .spyOn(api, "updateRoute")
      .mockResolvedValue({ ...ROUTE, default_driver_id: "d-1", auto_plan: true } as never);
    render(<RoutesPage />);
    const toggle = (await screen.findByLabelText("Plan R-01 every morning")) as HTMLInputElement;
    expect(toggle.disabled).toBe(false);
    fireEvent.click(toggle);
    await waitFor(() => expect(spy).toHaveBeenCalledWith("route-1", { auto_plan: true }));

    fireEvent.change(screen.getByLabelText("Default vehicle for R-01"), {
      target: { value: "" },
    });
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith("route-1", { clear_default_vehicle: true }),
    );
  });
});

/**
 * WO-108 · LACTEVA-LOGISTICS-003: the owner gives his delivery boy a round
 * without typing a code or leaving this page — the stops in delivery order
 * with up/down buttons, the default delivery boy from the LINKED drivers, how
 * the round goes out, and a hand-made profile linked to a login.
 */
describe("giving the delivery boy a round (WO-108)", () => {
  const LINKED = { id: "d-2", code: "RAMESH-PAWAR", full_name: "Ramesh Pawar", phone: "", user_id: "u-ramesh", center_id: null, active: true };

  it("edits the stops in delivery order with up/down buttons and saves the order", async () => {
    stubApi();
    vi.spyOn(api, "getRoute").mockResolvedValue({
      ...ROUTE,
      stops: [
        { customer_id: "c-flat", position: 1, code: "CUS-1", name: "Flat C-1603" },
        { customer_id: "c-temple", position: 2, code: "CUS-2", name: "Shri Ganesh Mandir" },
      ],
    } as never);
    vi.spyOn(api, "listCustomers").mockResolvedValue({
      items: [{ id: "c-hotel", code: "CUS-3", name: "Hotel Annapurna", customer_type: "hotel", status: "active" }],
      total: 1, limit: 8, offset: 0,
    } as never);
    const save = vi.spyOn(api, "setRouteStops").mockResolvedValue({ ...ROUTE, stops: [] } as never);
    render(<RoutesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit the stops of Kilima morning round" }));
    const list = await screen.findByRole("list", { name: "Stops" });
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(2));
    // The temple goes first: one tap on its up arrow.
    await userEvent.click(screen.getByRole("button", { name: "Move Shri Ganesh Mandir up" }));
    // And the hotel is added by name.
    await userEvent.type(screen.getByLabelText("Add a customer"), "Anna");
    await userEvent.click(await screen.findByRole("button", { name: /Hotel Annapurna/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save stops" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith("route-1", ["c-temple", "c-flat", "c-hotel"]));
  });

  it("offers only LINKED delivery boys as the round's default, and how the round goes out", async () => {
    stubApi();
    vi.spyOn(api, "listDrivers").mockResolvedValue([
      { id: "d-1", code: "DRV-1", full_name: "Joseph Mwangi", phone: "", user_id: null, center_id: null, active: true },
      LINKED,
    ] as never);
    const update = vi.spyOn(api, "updateRoute").mockResolvedValue(ROUTE as never);
    render(<RoutesPage />);
    const select = (await screen.findByLabelText("Default delivery boy for R-01")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["— none —", "Ramesh Pawar"]);
    await userEvent.selectOptions(select, "d-2");
    await waitFor(() => expect(update).toHaveBeenCalledWith("route-1", { default_driver_id: "d-2" }));
    await userEvent.selectOptions(screen.getByLabelText("How R-01 goes out"), "on_foot");
    await waitFor(() => expect(update).toHaveBeenCalledWith("route-1", { transport: "on_foot" }));
  });

  it("links a hand-made profile to a Delivery boy login from a select, by name", async () => {
    stubApi({
      members: [
        { user_id: "u-ramesh", status: "active", joined_at: "2026-09-26T00:00:00Z", roles: [{ name: "DRIVER", center_id: null }] },
        { user_id: "u-owner", status: "active", joined_at: "2026-09-26T00:00:00Z", roles: [{ name: "tenant-admin", center_id: null }] },
      ],
      userNames: { "u-ramesh": "Ramesh Pawar", "u-owner": "Sarwari Patel" },
    });
    const link = vi.spyOn(api, "linkDriverUser").mockResolvedValue(LINKED as never);
    render(<RoutesPage />);
    const select = (await screen.findByLabelText("Login for Joseph Mwangi")) as HTMLSelectElement;
    // Only the Delivery boy logins not yet on a profile — never the owner.
    await waitFor(() =>
      expect([...select.options].map((o) => o.textContent)).toEqual(["— no app login yet —", "Ramesh Pawar"]),
    );
    await userEvent.selectOptions(select, "u-ramesh");
    await waitFor(() => expect(link).toHaveBeenCalledWith("d-1", "u-ramesh"));
  });
});
