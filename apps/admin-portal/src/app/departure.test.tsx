/**
 * Somebody leaves (WO-88 §3): the departure checklist on Admin → Users.
 *
 *   * it reads what the person holds — a pending invitation, a driver
 *     profile, the routes that still name them as default driver, a
 *     household login — and lists what it will do;
 *   * it REFUSES to finish while an auto-planned route still names them,
 *     and finishes once the route is handed over or switched off;
 *   * finishing composes the existing calls, membership first, so the
 *     last-administrator refusal stops everything else;
 *   * it says what will NOT change, in the panel itself.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/admin/users",
  useSearchParams: () => new URLSearchParams(),
}));

import UsersPage from "@/app/admin/users/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const JOSEPH = {
  id: "u-2",
  email: "joseph@kilima.example",
  full_name: "Joseph Mwangi",
  locale: "en",
  is_active: true,
  last_login_at: null,
  created_at: "2026-09-01T00:00:00Z",
  customer_id: null as string | null,
};

const DRIVERS = [
  { id: "d-1", code: "DRV-1", full_name: "Joseph Mwangi", phone: "", user_id: "u-2", center_id: null, active: true },
  { id: "d-2", code: "DRV-2", full_name: "Peter Otieno", phone: "", user_id: null, center_id: null, active: true },
];

const ROUTE = {
  id: "r-1",
  code: "R-01",
  name: "Kilima morning round",
  center_id: null,
  active: true,
  notes: "",
  default_driver_id: "d-1",
  default_vehicle_id: null,
  auto_plan: true,
  stop_count: 12,
};

const INVITATION = {
  id: "inv-9",
  email: "joseph@kilima.example",
  role_name: "DRIVER",
  status: "pending",
  expires_at: "2026-10-01T00:00:00Z",
};

type Call = { url: string; method: string; body: unknown };

function stub(opts: {
  routes?: typeof ROUTE[];
  invitations?: typeof INVITATION[];
  user?: typeof JOSEPH;
  roles?: { name: string; center_id: string | null }[];
  suspend?: () => Response;
}) {
  const calls: Call[] = [];
  let routes = opts.routes ?? [];
  const user = opts.user ?? JOSEPH;
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url, method, body });
    if (path.endsWith("/v1/members") && method === "GET")
      return json([
        {
          user_id: "u-2",
          status: "active",
          joined_at: "2026-09-01T00:00:00Z",
          roles: opts.roles ?? [{ name: "DRIVER", center_id: null }],
          pending_email_change: null,
        },
      ]);
    if (path.endsWith("/v1/identity/users/u-2")) return json(user);
    if (path.includes("/v1/authz/roles")) return json([]);
    if (path.includes("/v1/collection-centers"))
      return json({ items: [], total: 0, limit: 100, offset: 0 });
    if (path.endsWith("/v1/invitations") && method === "GET") return json(opts.invitations ?? []);
    if (path.endsWith("/v1/drivers") && method === "GET") return json(DRIVERS);
    if (path.endsWith("/v1/drivers/d-1/default-routes")) return json(routes);
    if (path.endsWith("/v1/routes/r-1") && method === "PATCH") {
      routes = [];
      return json({ ...ROUTE, ...body });
    }
    if (path.endsWith("/v1/members/u-2/status") && method === "POST")
      return opts.suspend ? opts.suspend() : json({ user_id: "u-2", status: "suspended" });
    if (path.endsWith("/v1/invitations/inv-9") && method === "DELETE")
      return new Response(null, { status: 204 });
    if (path.endsWith("/v1/drivers/d-1/status") && method === "POST")
      return json({ ...DRIVERS[0], active: false });
    if (path.endsWith("/v1/customers/cu-7/bill-link") && method === "DELETE")
      return new Response(null, { status: 204 });
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return calls;
}


/** The alert that says something in particular (LACTEVA-QA-005): a page can
 *  hold more than one, so the singular query is never asked. */
async function alertSaying(pattern: RegExp, container: HTMLElement = document.body) {
  return waitFor(() => {
    const found = within(container)
      .getAllByRole("alert")
      .find((el) => pattern.test(el.textContent ?? ""));
    if (!found) throw new Error(`no alert yet matching ${pattern}`);
    return found;
  });
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

async function openChecklist() {
  const user = userEvent.setup();
  render(<UsersPage />);
  await screen.findByText("Joseph Mwangi");
  await user.click(screen.getByRole("button", { name: "Remove Joseph Mwangi from organisation" }));
  const panel = await screen.findByTestId("departure");
  await within(panel).findByTestId("departure-steps");
  return { user, panel };
}

describe("the departure checklist (WO-88 §3)", () => {
  it("lists what it will do, and will not finish while an auto-planned route still names them", async () => {
    stub({ routes: [ROUTE], invitations: [INVITATION] });
    const { panel } = await openChecklist();
    const steps = within(panel).getByTestId("departure-steps").textContent!;
    expect(steps).toMatch(/Suspend the membership — immediate/);
    expect(steps).toMatch(/Withdraw 1 pending invitation/);
    expect(steps).toMatch(/Retire driver profile DRV-1/);
    expect(within(panel).getByTestId("departure-route-R-01").textContent).toMatch(/auto-planned/);
    expect(within(panel).getByTestId("departure-finish")).toBeDisabled();
    expect(within(panel).getByTestId("departure-blocked").textContent).toMatch(
      /1 auto-planned route\(s\) still name them/,
    );
    // What will NOT change, in the panel itself.
    const unchanged = within(panel).getByTestId("departure-unchanged").textContent!;
    expect(unchanged).toMatch(/name stays on every delivery, run and audit line/);
    expect(unchanged).toMatch(/not reassigned to anyone/);
    expect(unchanged).toMatch(/reinstate this membership/);
  });

  it("hands the route to another driver, then finishes: membership first, then the rest", async () => {
    const calls = stub({ routes: [ROUTE], invitations: [INVITATION] });
    const { user, panel } = await openChecklist();
    await user.selectOptions(within(panel).getByLabelText("Hand R-01 to"), "d-2");
    await user.click(within(panel).getByRole("button", { name: "Hand over" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")).toMatchObject({
        url: "/api/proxy/v1/routes/r-1",
        body: { default_driver_id: "d-2" },
      }),
    );
    await waitFor(() => expect(within(panel).getByTestId("departure-finish")).toBeEnabled());
    expect(within(panel).queryByTestId("departure-blocked")).toBeNull();

    await user.click(within(panel).getByTestId("departure-finish"));
    await waitFor(() => expect(screen.queryByTestId("departure")).toBeNull());
    const writes = calls
      .filter((c) => c.method !== "GET")
      .map((c) => `${c.method} ${c.url.replace("/api/proxy", "")}`);
    expect(writes).toEqual([
      "PATCH /v1/routes/r-1",
      "POST /v1/members/u-2/status",
      "DELETE /v1/invitations/inv-9",
      "POST /v1/drivers/d-1/status",
    ]);
    expect(calls.find((c) => c.url.endsWith("/v1/members/u-2/status"))!.body).toEqual({
      status: "suspended",
    });
    expect(calls.find((c) => c.url.endsWith("/v1/drivers/d-1/status"))!.body).toEqual({
      active: false,
    });
    expect(
      (await screen.findByText(/Joseph Mwangi has left: membership suspended/)).textContent,
    ).toMatch(/driver DRV-1 retired/);
  });

  it("switching auto-planning off is the other way through", async () => {
    const calls = stub({ routes: [ROUTE] });
    const { user, panel } = await openChecklist();
    await user.click(within(panel).getByRole("button", { name: "Switch auto-planning off" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        auto_plan: false,
        clear_default_driver: true,
      }),
    );
    await waitFor(() => expect(within(panel).getByTestId("departure-finish")).toBeEnabled());
  });

  it("the last administrator's refusal stops everything, with the remedy on screen", async () => {
    const calls = stub({
      roles: [{ name: "tenant-admin", center_id: null }],
      suspend: () =>
        json(
          {
            title: "conflict",
            status: 409,
            detail:
              "this is the organisation's only administrator — invite another administrator first",
          },
          409,
        ),
    });
    const { user, panel } = await openChecklist();
    await user.click(within(panel).getByTestId("departure-finish"));
    expect(
      await alertSaying(/invite another administrator first/, panel),
    ).toBeInTheDocument();
    // Nothing after the refused step ran.
    expect(calls.filter((c) => c.method !== "GET").map((c) => c.url)).toEqual([
      "/api/proxy/v1/members/u-2/status",
    ]);
    expect(screen.getByTestId("departure")).toBeInTheDocument();
  });

  it("a household login's departure also revokes the household's bill link", async () => {
    const calls = stub({
      user: { ...JOSEPH, full_name: "Deshmukh household", customer_id: "cu-7" },
      roles: [{ name: "CUSTOMER_PORTAL", center_id: null }],
    });
    const user = userEvent.setup();
    render(<UsersPage />);
    await screen.findByText("Deshmukh household");
    await user.click(
      screen.getByRole("button", { name: "Remove Deshmukh household from organisation" }),
    );
    const panel = await screen.findByTestId("departure");
    expect((await within(panel).findByTestId("departure-steps")).textContent).toMatch(
      /Revoke the household's bill link/,
    );
    await user.click(within(panel).getByTestId("departure-finish"));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/v1/customers/cu-7/bill-link"))).toBe(true),
    );
  });
});
