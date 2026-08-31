/**
 * A dairy can register its own machines (WO-53 · LACTEVA-ADMIN-018).
 *
 * The registry has existed since P0-HW-001 with zero UI callers: a centre
 * could not register the scale that blocks its own sessions without curl and
 * a bearer token. These pin the screen that closes that, and — more usefully
 * — the three ways it could mislead: a failed list reading as an empty one,
 * controls offered to someone the platform will refuse, and a newly
 * registered device appearing active when it is not.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CenterDevices } from "@/components/center-devices";

const DEVICE = {
  id: "d1",
  center_id: "c1",
  category: "scale",
  name: "Intake bay scale",
  serial_number: "SC-0091",
  status: "active",
  make: "Essae",
  model: "DS-215",
};

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchSpy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/v1/devices?")) return json({ items: [DEVICE], total: 1 });
    return json(DEVICE);
  });
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the devices card", () => {
  it("names the machine, what it is, and that a scale blocks sessions", async () => {
    render(<CenterDevices centerId="c1" canManage />);
    expect(await screen.findByText("Intake bay scale")).toBeInTheDocument();
    // The label on the machine, which is what an operator matches against.
    expect(screen.getByText(/Essae DS-215/)).toBeInTheDocument();
    expect(screen.getByText(/SC-0091/)).toBeInTheDocument();
    // The platform's readiness rule, said out loud rather than discovered when
    // a session refuses to open.
    expect(screen.getByText("blocks sessions")).toBeInTheDocument();
  });

  it("offers no controls to someone the platform would refuse", async () => {
    // Absent, not disabled. A greyed-out Retire still tells a viewer the
    // capability exists and they are not trusted with it.
    render(<CenterDevices centerId="c1" canManage={false} />);
    await screen.findByText("Intake bay scale");
    expect(screen.queryByRole("button", { name: /Register a device/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Retire/ })).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("a list that failed to load does not read as a centre with no devices", async () => {
    fetchSpy.mockImplementation(async () => new Response("boom", { status: 500 }));
    render(<CenterDevices centerId="c1" canManage />);
    expect(await screen.findByText(/not the same as the centre having none/)).toBeInTheDocument();
    expect(screen.queryByText("No devices registered")).toBeNull();
  });

  it("says what an empty centre can and cannot do", async () => {
    fetchSpy.mockImplementation(async () => json({ items: [], total: 0 }));
    render(<CenterDevices centerId="c1" canManage />);
    expect(await screen.findByText("No devices registered")).toBeInTheDocument();
    // Manual capture is first-class; the honest consequence is only that a
    // session cannot open without a scale.
    expect(screen.getByText(/recorded by hand/)).toBeInTheDocument();
  });

  it("registers and assigns, and leaves activation as a separate decision", async () => {
    const user = userEvent.setup();
    render(<CenterDevices centerId="c1" canManage />);
    await screen.findByText("Intake bay scale");
    await user.click(screen.getByRole("button", { name: "Register a device" }));

    await user.type(screen.getByLabelText("Name"), "Analyzer A");
    await user.type(screen.getByLabelText("Serial number"), "AN-4410");
    await user.type(screen.getByLabelText("Make"), "Lactoscan");
    await user.click(screen.getByRole("button", { name: /Register and assign/ }));

    await waitFor(() => {
      const posts = fetchSpy.mock.calls.filter(
        (c) => (c[1] as RequestInit | undefined)?.method === "POST",
      );
      expect(posts.length).toBeGreaterThanOrEqual(2);
    });
    const bodies = fetchSpy.mock.calls
      .map((c) => (c[1] as RequestInit | undefined)?.body)
      .filter(Boolean)
      .map((b) => JSON.parse(String(b)));

    expect(bodies[0]).toMatchObject({
      category: "scale",
      name: "Analyzer A",
      serial_number: "AN-4410",
      make: "Lactoscan",
    });
    // Assigned, then stopped. Activating changes whether the centre may open
    // a session at all, so it is never a side effect of registering.
    expect(bodies[1]).toMatchObject({ center_id: "c1" });
    expect(bodies.some((b) => b.status === "active")).toBe(false);
  });

  it("refuses to register a device with no serial number", async () => {
    const user = userEvent.setup();
    render(<CenterDevices centerId="c1" canManage />);
    await screen.findByText("Intake bay scale");
    await user.click(screen.getByRole("button", { name: "Register a device" }));
    await user.type(screen.getByLabelText("Name"), "Nameless");
    await user.click(screen.getByRole("button", { name: /Register and assign/ }));

    expect(
      await screen.findByText(/how a reading is traced back to a machine/),
    ).toBeInTheDocument();
    expect(
      fetchSpy.mock.calls.filter(
        (c) => (c[1] as RequestInit | undefined)?.method === "POST",
      ),
    ).toHaveLength(0);
  });
});
