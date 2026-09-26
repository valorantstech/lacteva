/**
 * Each kind of user gets its own menu (WO-104 · LACTEVA-ADMIN-030).
 *
 * The owner's screenshot: a shop's owner signed in and saw twenty entries,
 * among them Organizations, Configuration, Sync and Roadmap — Lacteva's own
 * operator tools, offered because a tenant-admin holds the permissions for
 * them and the menu had only two axes, permission and module. The third axis
 * is WHO the page is for, and these tests pin the menu every kind of user is
 * offered against the registry the menu is built from, with the roles'
 * permission sets taken from the platform's own registry
 * (`system-roles.json`, exported by tools/authz/export_system_roles.py and
 * kept current by a backend test).
 *
 * Hiding is presentation. The routes and the permissions are unchanged.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => pathname.current,
  useSearchParams: () => new URLSearchParams(),
}));

import roles from "@/lib/system-roles.json";
import {
  AppShell,
  NAV_REGISTRY,
  isOwner,
  isPlatformSession,
  menuFor,
  mobileOnly,
} from "@/components/app-shell";
import type { Session } from "@/lib/api";

const ROLES = roles as Record<string, string[]>;

const ORGANIZATION = {
  id: "org-1",
  name: "Patel Dairy Shop and Sweets",
  slug: "patel",
  country_code: "IN",
  currency_code: "INR",
  currency_symbol: "₹",
  timezone: "Asia/Kolkata",
  default_language: "en",
  supported_languages: ["en"],
  languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
  quantity_unit: "litre",
  quantity_unit_label: "L",
};

/** A tenant user holding exactly the registry's permissions for `role`. */
function tenant(role: string, modules: string[], permissions = ROLES[role]): Session {
  expect(permissions, role).toBeDefined();
  return {
    authenticated: true,
    acting_tenant_id: null,
    user: { id: "u1", email: "sarwari@patel.example", full_name: "Sarwari Patel", locale: "en", is_active: true },
    tenant_id: "org-1",
    organization: { ...ORGANIZATION, modules },
    membership: null,
    roles: [{ name: role, description: "", center_id: null }],
    center_scope: null,
    permissions,
  } as unknown as Session;
}

/** Lacteva staff: no tenant bound, the wildcard. */
const PLATFORM: Session = {
  authenticated: true,
  acting_tenant_id: null,
  user: { id: "p1", email: "ops@lacteva.example", full_name: "Ops", locale: "en", is_active: true },
  tenant_id: null,
  organization: null,
  membership: null,
  roles: [],
  center_scope: null,
  permissions: ["*"],
} as unknown as Session;

const flat = (s: Session) => menuFor(s).flatMap((g) => g.entries);
const headings = (s: Session) => menuFor(s).map((g) => g.heading);

const COLLECTION = ["Collection centres", "Farmers", "Collections", "Day book", "Rate cards", "Matrices"];
const SALES = ["Customers", "Deliveries", "Month sheet", "Delivery rounds", "Bills", "Who owes money", "Products"];
const FINANCE = ["Settlements", "Farmer payments", "Receipts"];
const PLATFORM_TOOLS = ["Sync", "Playground", "Organizations", "Configuration", "Operations", "Roadmap"];

describe("the registry", () => {
  it("gives every entry an audience, and names the platform's own tools as such", () => {
    const all = NAV_REGISTRY.flatMap((g) => g.entries);
    for (const entry of all) expect(["platform", "business", "settings"], entry.href).toContain(entry.audience);
    const platform = all.filter((e) => e.audience === "platform").map((e) => e.href).sort();
    expect(platform).toEqual(
      ["/admin/configuration", "/admin/operations", "/admin/organizations", "/resolve", "/roadmap", "/sync"].sort(),
    );
    const settings = all.filter((e) => e.audience === "settings").map((e) => e.href).sort();
    expect(settings).toEqual(
      ["/admin/audit", "/admin/calendar", "/admin/roles", "/admin/settings", "/admin/subscription", "/admin/users"].sort(),
    );
  });
});

describe("the menus, per kind of user", () => {
  it("Lacteva platform admin: everything, the platform's tools last", () => {
    expect(menuFor(PLATFORM)).toEqual([
      { heading: null, entries: ["Dashboard"] },
      { heading: "Collection", entries: COLLECTION },
      { heading: "Sales", entries: SALES },
      { heading: "Finance", entries: FINANCE },
      { heading: null, entries: ["Reports", "Notifications"] },
      { heading: "Settings", entries: ["Staff", "Dairy settings", "Business calendar", "Roles", "Plan", "Activity log"] },
      { heading: "Platform", entries: PLATFORM_TOOLS },
    ]);
  });

  it("shop owner (tenant-admin, sales only): the shop, then Settings — no Platform heading", () => {
    const owner = tenant("tenant-admin", ["sales"]);
    expect(menuFor(owner)).toEqual([
      { heading: null, entries: ["Dashboard"] },
      { heading: "Sales", entries: SALES },
      { heading: null, entries: ["Reports", "Notifications"] },
      { heading: "Settings", entries: ["Staff", "Shop settings", "Plan"] },
    ]);
    expect(headings(owner)).not.toContain("Platform");
    for (const hidden of ["Roles", "Organizations", "Audit", "Activity log", "Configuration", "Sync", "Business calendar", "Roadmap", "Playground"]) {
      expect(flat(owner), hidden).not.toContain(hidden);
    }
  });

  it("dairy firm owner (tenant-admin, collection): intake, money, then Settings with the calendar and Roles", () => {
    const owner = tenant("tenant-admin", ["collection"]);
    expect(menuFor(owner)).toEqual([
      { heading: null, entries: ["Dashboard"] },
      { heading: "Collection", entries: COLLECTION },
      { heading: "Finance", entries: FINANCE },
      { heading: null, entries: ["Reports", "Notifications"] },
      { heading: "Settings", entries: ["Staff", "Dairy settings", "Business calendar", "Roles", "Plan"] },
    ]);
  });

  it("an owner who does both: the union, sales after collection", () => {
    const owner = tenant("tenant-admin", ["collection", "sales"]);
    expect(flat(owner)).toEqual([
      "Dashboard", ...COLLECTION, ...SALES, ...FINANCE, "Reports", "Notifications",
      "Staff", "Dairy settings", "Business calendar", "Roles", "Plan",
    ]);
    // ORGANIZATION_ADMIN is the same person under the registry's other name.
    expect(menuFor(tenant("ORGANIZATION_ADMIN", ["collection", "sales"]))).toEqual(menuFor(owner));
  });

  it("centre manager: their intake, and what their reads reach", () => {
    expect(flat(tenant("CENTRE_MANAGER", ["collection"]))).toEqual([
      "Dashboard", "Collection centres", "Farmers", "Collections", "Day book", "Settlements", "Reports",
    ]);
  });

  it("finance manager: bills, who owes money, settlements, payments, receipts, reports", () => {
    expect(flat(tenant("FINANCE_MANAGER", ["collection", "sales"]))).toEqual([
      "Dashboard", "Collection centres", "Farmers", "Collections",
      "Customers", "Deliveries", "Month sheet", "Bills", "Who owes money", "Products",
      "Settlements", "Farmer payments", "Receipts", "Reports",
    ]);
  });

  it("sales officer: customers, deliveries, the month sheet, rounds and bills", () => {
    expect(flat(tenant("SALES_OFFICER", ["sales"]))).toEqual([
      "Dashboard", ...SALES, "Reports",
    ]);
    // At a firm that only collects, a sales officer has nothing to sell.
    expect(flat(tenant("SALES_OFFICER", ["collection"]))).toEqual(["Dashboard", "Reports"]);
  });

  it("auditor: everything their reads reach, read-only, and the activity log in the menu", () => {
    const auditor = tenant("AUDITOR", ["collection", "sales"]);
    expect(flat(auditor)).toContain("Activity log");
    expect(flat(auditor)).toContain("Reports");
    expect(headings(auditor)).not.toContain("Platform");
    expect(isOwner(auditor)).toBe(false);
  });

  it("collection operator, driver and customer: no menu — their work is the handset", () => {
    for (const role of ["COLLECTION_OPERATOR", "DRIVER", "CUSTOMER_PORTAL"]) {
      const s = tenant(role, ["collection", "sales"]);
      expect(mobileOnly(s), role).toBe(true);
      expect(menuFor(s), role).toEqual([]);
    }
    // A manager who ALSO drives is not a handset-only person.
    const both = { ...tenant("DRIVER", ["sales"]), roles: [{ name: "DRIVER" }, { name: "SALES_OFFICER" }] } as unknown as Session;
    expect(mobileOnly(both)).toBe(false);
  });
});

describe("the audience rule", () => {
  it("a tenant user never sees a platform entry — not even holding every permission", () => {
    const godlike = tenant("tenant-admin", ["collection", "sales"], ["*"]);
    expect(isPlatformSession(godlike)).toBe(false);
    for (const tool of PLATFORM_TOOLS) expect(flat(godlike), tool).not.toContain(tool);
    expect(headings(godlike)).not.toContain("Platform");
  });

  it("a platform session still sees everything, acting in an organisation or not", () => {
    expect(flat(PLATFORM)).toEqual(expect.arrayContaining(PLATFORM_TOOLS));
    const acting = { ...PLATFORM, acting_tenant_id: "org-1" } as Session;
    expect(flat(acting)).toEqual(flat(PLATFORM));
  });

  it("the owner reaches the activity log from Settings, not the menu; a viewer has it in the menu", () => {
    expect(isOwner(tenant("tenant-admin", ["sales"]))).toBe(true);
    expect(flat(tenant("tenant-admin", ["collection", "sales"]))).not.toContain("Activity log");
    expect(flat(tenant("tenant-viewer", ["collection", "sales"]))).toContain("Activity log");
  });
});

describe("the shell", () => {
  const json = (body: unknown) =>
    new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  beforeEach(() => {
    pathname.current = "/";
    vi.unstubAllGlobals();
  });
  afterEach(() => vi.unstubAllGlobals());

  function stub(session: Session) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/api/auth/session") ? json(session) : json({ items: [], total: 0 }),
      ),
    );
  }

  it("draws the shop owner's menu with Settings as its only heading, and says Owner under the name", async () => {
    stub(tenant("tenant-admin", ["sales"]));
    render(<AppShell><div>PAGE</div></AppShell>);
    expect(await screen.findByRole("link", { name: "Customers" })).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0];
    const shown = [...nav.querySelectorAll("p")].map((p) => p.textContent);
    expect(shown).toEqual(["Sales", "Settings"]);
    expect(screen.queryByRole("link", { name: "Organizations" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Configuration" })).toBeNull();
    expect(screen.getByRole("link", { name: "Shop settings" })).toBeInTheDocument();
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.queryByText("Tenant Admin")).toBeNull();
  });

  it("a driver signing in to the portal gets one line and the app link, not an empty rail", async () => {
    stub(tenant("DRIVER", ["sales"]));
    render(<AppShell><div>OFFICE FORMS</div></AppShell>);
    expect(await screen.findByTestId("mobile-only")).toHaveTextContent("Lacteva app");
    expect(screen.getByRole("link", { name: "About the Lacteva app" })).toHaveAttribute("href", "https://lacteva.com/product");
    expect(screen.queryByText("OFFICE FORMS")).toBeNull();
    expect(screen.queryByRole("link", { name: "Dashboard" })).toBeNull();
    expect(screen.getByText("Driver")).toBeInTheDocument();
  });
});
