/**
 * PORTAL-001 / F-09 + F-10 — the administrative surfaces, and the tenant
 * context every page depends on.
 *
 * These pages change who can do what, so the assertions are about the
 * consequences an administrator is shown, not about markup.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

import AuditPage from "@/app/admin/audit/page";
import OrganizationsPage from "@/app/admin/organizations/page";
import UsersPage from "@/app/admin/users/page";

/** Route a fake platform by URL, so a page's real call graph is exercised. */
function routeFetch(routes: Record<string, unknown>, status = 200) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = Object.keys(routes).find((key) => url.includes(key));
    if (!match) {
      return new Response(JSON.stringify({ title: "not_found", detail: "No route." }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(routes[match]), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("users", () => {
  const people = {
    "/v1/members": [{ user_id: "u1", status: "active", joined_at: "2026-01-01T00:00:00Z" }],
    "/v1/identity/users/u1": {
      id: "u1",
      email: "leaver@kilima.example",
      full_name: "A Leaver",
      locale: "en",
      is_active: true,
    },
  };

  it("lists the tenant's people with their account state", async () => {
    routeFetch(people);
    render(<UsersPage />);
    expect(await screen.findByText("leaver@kilima.example")).toBeInTheDocument();
    expect(screen.getByText("A Leaver")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deactivate" })).toBeInTheDocument();
  });

  it("deactivates a user and says plainly that sessions were revoked", async () => {
    const fetchSpy = routeFetch({
      ...people,
      "/v1/identity/users/u1/status": { ...people["/v1/identity/users/u1"], is_active: false },
    });
    const user = userEvent.setup();

    render(<UsersPage />);
    await user.click(await screen.findByRole("button", { name: "Deactivate" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/every live session was revoked/i),
    );
    const call = fetchSpy.mock.calls.find(([url]) => String(url).includes("/status"));
    expect(call).toBeDefined();
  });

  it("keeps a member whose account cannot be read, rather than silently shortening the list", async () => {
    routeFetch({ "/v1/members": [{ user_id: "gone", status: "active", joined_at: "2026-01-01T00:00:00Z" }] });
    render(<UsersPage />);
    expect(await screen.findByText("account unavailable")).toBeInTheDocument();
  });

  it("surfaces an API error instead of rendering an empty table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "You do not have permission." }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(<UsersPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission.");
  });
});

describe("organization / tenant context", () => {
  it("shows the tenant this session acts inside and the permissions it carries", async () => {
    routeFetch({
      "/v1/auth/me": {
        user: { id: "u1", email: "boss@kilima.example", full_name: "Boss", locale: "en", is_active: true },
        tenant_id: "org-1",
        permissions: ["identity.user.manage", "authz.role.manage"],
      },
      "/v1/organizations/org-1": {
        id: "org-1",
        name: "Kilima Dairy Cooperative",
        slug: "kilima",
        country_code: "ke",
      },
    });
    render(<OrganizationsPage />);
    expect(await screen.findByText("Kilima Dairy Cooperative")).toBeInTheDocument();
    expect(screen.getByText("KE")).toBeInTheDocument();
    expect(screen.getByText("identity.user.manage")).toBeInTheDocument();
  });

  it("explains a platform-level session rather than showing a blank organization", async () => {
    routeFetch({
      "/v1/auth/me": {
        user: { id: "u1", email: "root@example.com", full_name: "Root", locale: "en", is_active: true },
        tenant_id: null,
        permissions: ["*"],
      },
    });
    render(<OrganizationsPage />);
    expect(await screen.findByText(/platform-level session/i)).toBeInTheDocument();
  });
});

describe("audit", () => {
  it("shows grants and revocations together — the pair an access review reads", async () => {
    routeFetch({
      "/v1/audit": [
        {
          id: "a1",
          action: "authz.role.granted",
          resource_type: "user_role",
          resource_id: "r1",
          actor_id: "u9",
          created_at: "2026-08-09T10:00:00Z",
          detail: { user_id: "u1" },
        },
        {
          id: "a2",
          action: "authz.role.revoked",
          resource_type: "user_role",
          resource_id: "r1",
          actor_id: "u9",
          created_at: "2026-08-09T11:00:00Z",
          detail: null,
        },
      ],
    });
    render(<AuditPage />);
    expect(await screen.findByText("authz.role.granted")).toBeInTheDocument();
    expect(screen.getByText("authz.role.revoked")).toBeInTheDocument();
  });

  it("filters by action", async () => {
    routeFetch({
      "/v1/audit": [
        { id: "a1", action: "authz.role.granted", resource_type: "user_role", resource_id: null, actor_id: null, created_at: "2026-08-09T10:00:00Z", detail: null },
        { id: "a2", action: "payment.completed", resource_type: "payment", resource_id: null, actor_id: null, created_at: "2026-08-09T10:00:00Z", detail: null },
      ],
    });
    const user = userEvent.setup();
    render(<AuditPage />);
    await screen.findByText("authz.role.granted");
    await user.type(screen.getByLabelText(/filter/i), "payment");
    await waitFor(() => expect(screen.queryByText("authz.role.granted")).not.toBeInTheDocument());
    expect(screen.getByText("payment.completed")).toBeInTheDocument();
  });
});

describe("navigation (NAV-001)", () => {
  const USER = { id: "u1", email: "boss@kilima.example", full_name: "Boss", locale: "en", is_active: true };
  const ALL = [
    "collection.center.read", "supplier.read", "collection.transaction.read",
    "pricing.ratecard.read", "settlement.read", "payment.read", "receipt.read",
    "reporting.read", "notification.read", "sync.read", "identity.user.read",
    "authz.role.read", "organization.read", "audit.read", "configuration.read",
    "platform.relay.manage",
  ];
  const SIGNED_IN = {
    "/api/auth/session": {
      authenticated: true,
      user: USER,
      tenant_id: "org-1",
      acting_tenant_id: null,
      permissions: ALL,
    },
  };

  it("shows no destinations to a signed-out visitor — every one of them needs a session", async () => {
    const { AppShell } = await import("@/components/app-shell");
    routeFetch({ "/api/auth/session": { authenticated: false } });

    render(<AppShell>{null}</AppShell>);
    expect(await screen.findByRole("link", { name: /sign in/i })).toBeInTheDocument();
    for (const label of ["Centers", "Suppliers", "Settlements", "Users", "Audit"]) {
      expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
    // The product name stays: it is the way back to a known page.
    expect(screen.getByRole("link", { name: "Lacteva" })).toBeInTheDocument();
  });

  it("shows only what this session may use — a viewer is not offered Users (PERM-001)", async () => {
    const { AppShell } = await import("@/components/app-shell");
    routeFetch({
      "/api/auth/session": {
        authenticated: true,
        user: USER,
        tenant_id: "org-1",
        acting_tenant_id: null,
        permissions: ["collection.center.read", "supplier.read"],
      },
    });

    render(<AppShell>{null}</AppShell>);
    expect(await screen.findByRole("link", { name: "Centers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Suppliers" })).toBeInTheDocument();
    for (const hidden of ["Users", "Roles", "Audit", "Settlements", "Payments"]) {
      expect(screen.queryByRole("link", { name: hidden })).not.toBeInTheDocument();
    }
  });

  it("treats the platform wildcard as every permission", async () => {
    const { AppShell } = await import("@/components/app-shell");
    routeFetch({
      "/api/auth/session": {
        authenticated: true,
        user: USER,
        tenant_id: null,
        acting_tenant_id: "org-9",
        permissions: ["*"],
      },
    });

    render(<AppShell>{null}</AppShell>);
    expect(await screen.findByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Centers" })).toBeInTheDocument();
  });

  it("asks a platform session with no organization to choose one (TENANT-001)", async () => {
    const { AppShell } = await import("@/components/app-shell");
    routeFetch({
      "/api/auth/session": {
        authenticated: true,
        user: USER,
        tenant_id: null,
        acting_tenant_id: null,
        permissions: ["*"],
      },
    });

    render(<AppShell>{null}</AppShell>);
    expect(await screen.findByLabelText("Organization ID")).toBeInTheDocument();
    expect(screen.getByText(/choose an organization/i)).toBeInTheDocument();
  });

  it("does not ask a tenant-scoped session to choose an organization", async () => {
    const { AppShell } = await import("@/components/app-shell");
    routeFetch(SIGNED_IN);

    render(<AppShell>{null}</AppShell>);
    await screen.findByRole("link", { name: "Centers" });
    expect(screen.queryByLabelText("Organization ID")).not.toBeInTheDocument();
  });

  it("shows the menu once there is a session", async () => {
    const { AppShell } = await import("@/components/app-shell");
    routeFetch(SIGNED_IN);

    render(<AppShell>{null}</AppShell>);
    expect(await screen.findByRole("link", { name: "Centers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settlements" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();
  });

  it("shows nothing at all until the answer is known, rather than flashing a menu", async () => {
    const { AppShell } = await import("@/components/app-shell");
    // A probe that never resolves: the bar must stay quiet, not guess.
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    render(<AppShell>{null}</AppShell>);
    expect(screen.queryByRole("link", { name: "Centers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lacteva" })).toBeInTheDocument();
  });

  it("signs out through the route handler and hides the menu again", async () => {
    const { AppShell } = await import("@/components/app-shell");
    const fetchSpy = routeFetch({ ...SIGNED_IN, "/api/auth/logout": {} });
    const user = userEvent.setup();

    render(<AppShell>{null}</AppShell>);
    await user.click(await screen.findByRole("button", { name: /sign out/i }));

    await waitFor(() =>
      expect(fetchSpy.mock.calls.some(([url]) => String(url) === "/api/auth/logout")).toBe(true),
    );
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "Centers" })).not.toBeInTheDocument(),
    );
  });
});

describe("a representative business page", () => {
  it("renders the centers it is given", async () => {
    const CentersPage = (await import("@/app/centers/page")).default;
    routeFetch({
      "/v1/collection-centers": {
        items: [
          {
            id: "c1",
            branch_id: "b1",
            name: "Kilima Center",
            code: "KH-C1",
            status: "active",
            timezone: "Africa/Nairobi",
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      },
      "/v1/branches": [{ id: "b1", workspace_id: "w1", name: "Kilima Hill", code: "KH", status: "active" }],
    });

    render(<CentersPage />);
    const row = await screen.findByText("Kilima Center");
    expect(row).toBeInTheDocument();
    expect(within(row.closest("tr")!).getByText("KH-C1")).toBeInTheDocument();
  });
});
