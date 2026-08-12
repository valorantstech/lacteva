/**
 * Roles, users and permission-aware navigation (DEMO-008).
 *
 * The portal's job in an RBAC system is to be a good citizen, not a guard: it
 * shows what a person can do so they are not led into refusals. These tests
 * defend that it reads the answer from the backend rather than deciding it —
 * the failure mode being a role name compiled into the bundle, which is
 * exactly the defect this work order found on the Roles page.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/roles",
}));

import RolesPage from "@/app/admin/roles/page";
import UsersPage from "@/app/admin/users/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const ROLES = [
  {
    id: "r1",
    name: "COLLECTION_OPERATOR",
    description: "System role COLLECTION_OPERATOR",
    tenant_id: null,
    system: true,
    permissions: ["collection.transaction.record", "supplier.read"],
    assignments: 3,
  },
  {
    id: "r2",
    name: "FINANCE_MANAGER",
    description: "System role FINANCE_MANAGER",
    tenant_id: null,
    system: true,
    permissions: ["settlement.finalize", "payment.manage"],
    assignments: 1,
  },
  {
    id: "r3",
    name: "weighbridge-supervisor",
    description: "",
    tenant_id: "org-1",
    system: false,
    permissions: ["collection.transaction.read"],
    assignments: 0,
  },
];

const CENTERS = {
  items: [
    { id: "c1", branch_id: "b1", name: "Kilima Hill", code: "KH-C1", status: "active", timezone: "UTC" },
    { id: "c2", branch_id: "b1", name: "Naivasha Lakeside", code: "NL-C1", status: "active", timezone: "UTC" },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

const MEMBERS = [
  {
    user_id: "u1",
    status: "active",
    joined_at: "2026-01-01T00:00:00Z",
    roles: [{ name: "ORGANIZATION_ADMIN", center_id: null }],
  },
  {
    user_id: "u2",
    status: "suspended",
    joined_at: "2026-02-01T00:00:00Z",
    roles: [{ name: "CENTRE_MANAGER", center_id: "c1" }],
  },
];

const USERS: Record<string, unknown> = {
  u1: {
    id: "u1",
    email: "admin@kilima.example",
    full_name: "Wanjiku Mbugua",
    locale: "en",
    is_active: true,
    last_login_at: "2026-08-12T09:15:00Z",
  },
  u2: {
    id: "u2",
    email: "centre@kilima.example",
    full_name: "Otieno Odhiambo",
    locale: "en",
    is_active: true,
    last_login_at: null,
  },
};

function routeAll(overrides: Record<string, (url: string) => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler(url);
    }
    if (init?.method === "POST" || init?.method === "DELETE") return json({ ok: true });
    if (path.endsWith("/v1/authz/roles")) return json(ROLES);
    if (path.endsWith("/v1/authz/permissions"))
      return json({
        "collection.transaction.record": "Record milk collection transactions",
        "settlement.finalize": "Finalize settlements (makes them immutable)",
      });
    if (path.endsWith("/v1/members")) return json(MEMBERS);
    if (path.includes("/v1/identity/users/")) return json(USERS[path.split("/").pop()!]);
    if (path.endsWith("/v1/collection-centers")) return json(CENTERS);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

const urls = (spy: ReturnType<typeof routeAll>) => spy.mock.calls.map((c) => String(c[0]));

describe("roles page", () => {
  it("lists the roles the PLATFORM has, not a list compiled into the bundle", async () => {
    routeAll();
    render(<RolesPage />);

    // Scoped to the TABLE: each name also appears in the grant dropdown.
    expect(await screen.findByRole("cell", { name: "COLLECTION_OPERATOR" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "FINANCE_MANAGER" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "weighbridge-supervisor" })).toBeInTheDocument();
    // The role the old page offered and the backend never had.
    expect(screen.queryByText("tenant-operator")).not.toBeInTheDocument();
  });

  it("distinguishes a platform role from one this organization defined", async () => {
    routeAll();
    render(<RolesPage />);
    await screen.findByRole("cell", { name: "COLLECTION_OPERATOR" });
    expect(screen.getAllByText("platform").length).toBe(2);
    expect(screen.getByText("this organization")).toBeInTheDocument();
  });

  it("shows how many people hold a role, and what it actually grants", async () => {
    routeAll();
    render(<RolesPage />);
    const row = (
      await screen.findByRole("cell", { name: "COLLECTION_OPERATOR" })
    ).closest("tr") as HTMLElement;
    expect(within(row).getByText("3")).toBeInTheDocument();
    expect(within(row).getByText("2")).toBeInTheDocument(); // permission count

    // Expanding reveals the permission KEYS the role actually carries. The
    // same key also names a checkbox in the "define a role" list below, so the
    // assertion counts rather than assuming one.
    const before = screen.getAllByText("collection.transaction.record").length;
    await userEvent.click(within(row).getByRole("button", { name: "Show" }));
    await waitFor(() =>
      expect(screen.getAllByText("collection.transaction.record").length).toBe(before + 1),
    );
    expect(screen.getByText("supplier.read")).toBeInTheDocument();
  });

  it("grants a role at a CENTRE scope when one is chosen", async () => {
    const spy = routeAll();
    render(<RolesPage />);
    await screen.findByRole("cell", { name: "COLLECTION_OPERATOR" });

    await userEvent.selectOptions(screen.getByLabelText("User"), "u1");
    await userEvent.selectOptions(screen.getByLabelText("Role"), "COLLECTION_OPERATOR");
    await userEvent.selectOptions(screen.getByLabelText("Centre scope"), "c1");
    await userEvent.click(screen.getByRole("button", { name: "Grant" }));

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) => String(u).endsWith("/v1/authz/assignments"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call![1]!.body))).toEqual({
        user_id: "u1",
        role_name: "COLLECTION_OPERATOR",
        center_id: "c1",
      });
    });
  });

  it("omits the centre entirely for an organization-wide grant", async () => {
    const spy = routeAll();
    render(<RolesPage />);
    await screen.findByRole("cell", { name: "COLLECTION_OPERATOR" });

    await userEvent.selectOptions(screen.getByLabelText("User"), "u1");
    await userEvent.selectOptions(screen.getByLabelText("Role"), "FINANCE_MANAGER");
    await userEvent.click(screen.getByRole("button", { name: "Grant" }));

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) => String(u).endsWith("/v1/authz/assignments"));
      expect(JSON.parse(String(call![1]!.body))).toEqual({
        user_id: "u1",
        role_name: "FINANCE_MANAGER",
      });
    });
  });

  it("reads the role list from the API on every load", async () => {
    const spy = routeAll();
    render(<RolesPage />);
    await screen.findByRole("cell", { name: "COLLECTION_OPERATOR" });
    expect(urls(spy).some((u) => u.includes("/v1/authz/roles"))).toBe(true);
  });
});

describe("users page", () => {
  it("shows each person's role and its centre scope, by name", async () => {
    routeAll();
    render(<UsersPage />);

    expect(await screen.findByText("Wanjiku Mbugua")).toBeInTheDocument();
    expect(screen.getByText("ORGANIZATION_ADMIN")).toBeInTheDocument();
    expect(screen.getByText("· whole organization")).toBeInTheDocument();
    expect(screen.getByText("CENTRE_MANAGER")).toBeInTheDocument();
    // The scope is shown as a centre NAME, not a uuid.
    expect(screen.getByText("· Kilima Hill")).toBeInTheDocument();
  });

  it("shows when each account last signed in, and says so when it never has", async () => {
    routeAll();
    render(<UsersPage />);
    await screen.findByText("Wanjiku Mbugua");
    expect(screen.getByText("2026-08-12 09:15")).toBeInTheDocument();
    expect(screen.getByText("never")).toBeInTheDocument();
  });

  it("suspends a membership through the platform, and says when it takes effect", async () => {
    const spy = routeAll();
    render(<UsersPage />);
    await screen.findByText("Wanjiku Mbugua");

    const row = screen.getByText("Wanjiku Mbugua").closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Suspend" }));

    await waitFor(() => {
      const call = spy.mock.calls.find(([u]) => String(u).endsWith("/v1/members/u1/status"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call![1]!.body))).toEqual({ status: "suspended" });
    });
    expect(await screen.findByText(/applies to their very next request/)).toBeInTheDocument();
  });

  it("offers to reinstate a member who is already suspended", async () => {
    routeAll();
    render(<UsersPage />);
    await screen.findByText("Otieno Odhiambo");
    const row = screen.getByText("Otieno Odhiambo").closest("tr") as HTMLElement;
    expect(within(row).getByRole("button", { name: "Reinstate" })).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Suspend" })).not.toBeInTheDocument();
  });
});
