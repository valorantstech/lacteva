/**
 * The organisation says which modules it runs (D-31 · WO-85).
 *
 * Owner decision D-31: "dont remove what we have created earlier … some
 * dairy firm also have retail, they sell and purchase both. so make
 * everything customizable." So the navigation is the union of what the
 * enabled modules contribute, asserted here against THE registry the menu
 * is built from, not a copy:
 *
 *   * both modules → byte-for-byte what a tenant-admin sees today;
 *   * `["sales"]` → no Settlements, Rate cards, Suppliers, Day book,
 *     Payments or Receipts;
 *   * `["collection"]` → no Customers, Deliveries, Routes, Billing or
 *     Who owes money;
 *   * a session with no organisation block is not a shop — it sees all;
 *   * the words change only where they are wrong, only for sales-only;
 *   * Settings has the two switches and says hiding deletes nothing;
 *   * the dashboard shows the halves the organisation has.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => pathname.current,
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell, NAV_REGISTRY, navVisibleTo } from "@/components/app-shell";
import OrganizationSettingsPage from "@/app/admin/settings/page";
import { translatorFor } from "@/lib/i18n";
import { enabledModules, salesOnly } from "@/lib/modules";
import { CATALOGS } from "@/lib/messages";
import type { Session } from "@/lib/api";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const ORGANIZATION = {
  id: "org-1",
  name: "Sitara Dairy",
  slug: "sitara",
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

function session(modules?: string[]): Session {
  return {
    authenticated: true,
    acting_tenant_id: null,
    user: { id: "u1", email: "owner@sitara.example", full_name: "Owner", locale: "en", is_active: true },
    tenant_id: "org-1",
    organization: modules ? { ...ORGANIZATION, modules } : ORGANIZATION,
    membership: null,
    roles: [{ name: "tenant-admin", description: "", center_id: null }],
    center_scope: null,
    customer_id: null,
    permissions: ["*"],
  } as unknown as Session;
}

/** Every label the menu offers a session, from the registry and its rule. */
function offered(s: Session): string[] {
  const t = translatorFor("en");
  return NAV_REGISTRY.flatMap((group) =>
    group.entries.filter((e) => navVisibleTo(s, e)).map((e) => t(e.labelKey)),
  );
}

// WO-104: a tenant-admin with both modules. In the business's words, grouped
// by the day's work, Settings at the bottom — and none of the platform's own
// tools (Sync, Playground, Organizations, Configuration, Operations, Roadmap),
// which only a platform session is offered now. `menus.test.tsx` pins every
// kind of user; this file keeps the MODULE axis honest.
const EVERYTHING = [
  "Dashboard",
  "Collection centres", "Farmers", "Collections", "Day book", "Rate cards", "Matrices",
  "Customers", "Deliveries", "Month sheet", "Delivery rounds", "Bills", "Who owes money", "Products",
  "Settlements", "Farmer payments", "Receipts",
  "Reports", "Notifications",
  "Staff", "Dairy settings", "Business calendar", "Roles", "Plan",
];

describe("the registry", () => {
  it("names a module on every collection and sales destination, and on nothing shared", () => {
    const byHref = Object.fromEntries(
      NAV_REGISTRY.flatMap((g) => g.entries.map((e) => [e.href, e.module ?? null])),
    );
    for (const href of ["/centers", "/suppliers", "/transactions", "/day-book", "/rate-cards", "/matrices", "/resolve", "/settlements", "/payments", "/receipts"]) {
      expect(byHref[href], href).toBe("collection");
    }
    for (const href of ["/customers", "/deliveries", "/deliveries/month", "/routes", "/billing", "/receivables", "/admin/products"]) {
      expect(byHref[href], href).toBe("sales");
    }
    for (const href of ["/", "/reports", "/notifications", "/sync", "/admin/users", "/admin/settings", "/admin/audit", "/admin/subscription"]) {
      expect(byHref[href], href).toBeNull();
    }
    // WO-104: two settings pages belong to firms that collect — holidays
    // decide collection days, and custom roles are a firm's thing.
    expect(byHref["/admin/calendar"]).toBe("collection");
    expect(byHref["/admin/roles"]).toBe("collection");
  });
});

describe("what a tenant-admin is offered", () => {
  it("both modules: identical to today", () => {
    expect(offered(session(["collection", "sales"]))).toEqual(EVERYTHING);
  });

  it("no organisation block, or no list: identical to today (nothing said is not a shop)", () => {
    expect(offered(session())).toEqual(EVERYTHING);
    expect(offered(session([]))).toEqual(EVERYTHING);
    expect(enabledModules(null)).toEqual(new Set(["collection", "sales"]));
  });

  it("a milk shop: no Settlements, Rate cards, Farmers, Day book, Farmer payments or Receipts", () => {
    const labels = offered(session(["sales"]));
    for (const hidden of ["Settlements", "Rate cards", "Matrices", "Playground", "Farmers", "Collection centres", "Collections", "Day book", "Farmer payments", "Receipts", "Business calendar", "Roles"]) {
      expect(labels, hidden).not.toContain(hidden);
    }
    for (const shown of ["Dashboard", "Customers", "Deliveries", "Delivery rounds", "Bills", "Who owes money", "Products", "Reports", "Notifications", "Staff", "Dairy settings", "Plan"]) {
      expect(labels, shown).toContain(shown);
    }
  });

  it("a classic dairy: no Customers, Deliveries, Delivery rounds, Bills or Who owes money", () => {
    const labels = offered(session(["collection"]));
    for (const hidden of ["Customers", "Deliveries", "Month sheet", "Delivery rounds", "Bills", "Who owes money", "Products"]) {
      expect(labels, hidden).not.toContain(hidden);
    }
    for (const shown of ["Collection centres", "Farmers", "Settlements", "Rate cards", "Farmer payments", "Receipts", "Reports", "Business calendar", "Roles"]) {
      expect(labels, shown).toContain(shown);
    }
  });

  it("permission still comes first: a shop's viewer without users.read is not offered Staff", () => {
    const viewer = { ...session(["sales"]), permissions: ["sales.customer.read"] } as Session;
    const labels = offered(viewer);
    expect(labels).toContain("Customers");
    expect(labels).not.toContain("Staff");
    expect(labels).not.toContain("Deliveries");
  });
});

describe("the words", () => {
  it("say Shop only for an organisation that sells and does not collect", () => {
    expect(salesOnly(session(["sales"]))).toBe(true);
    expect(salesOnly(session(["collection", "sales"]))).toBe(false);
    expect(salesOnly(session())).toBe(false);
    const shop = translatorFor("en", { salesOnly: true });
    const dairy = translatorFor("en");
    expect(shop("entity.center")).toBe("Shop");
    expect(dairy("entity.center")).toBe("Collection centre");
    expect(shop("dashboard.heroTitle")).toBe("The shop, this morning");
    // WO-104: a shop's settings are the shop's.
    expect(shop("nav.settings")).toBe("Shop settings");
    expect(dairy("nav.settings")).toBe("Dairy settings");
    // Every key without an override falls through.
    expect(shop("nav.customers")).toBe(dairy("nav.customers"));
    expect(shop("settlement.subtitle")).toBe(dairy("settlement.subtitle"));
    // And Hindi has the same overrides, no more.
    const hi = translatorFor("hi", { salesOnly: true });
    expect(hi("entity.center")).toBe("दुकान");
    expect(hi("nav.customers")).toBe(CATALOGS.hi["nav.customers"]);
  });
});

describe("the shell", () => {
  beforeEach(() => {
    pathname.current = "/";
    vi.unstubAllGlobals();
  });
  afterEach(() => vi.unstubAllGlobals());

  function stubSession(modules: string[]) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).includes("/api/auth/session")
          ? json(session(modules))
          : json({ items: [], total: 0 }),
      ),
    );
  }

  it("draws a shop's menu without the intake side", async () => {
    stubSession(["sales"]);
    render(<AppShell><div>PAGE</div></AppShell>);
    expect(await screen.findByRole("link", { name: "Customers" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settlements" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Farmers" })).toBeNull();
    expect(screen.getByRole("link", { name: "Products" })).toBeInTheDocument();
  });

  it("draws a dairy that does both exactly as before", async () => {
    stubSession(["collection", "sales"]);
    render(<AppShell><div>PAGE</div></AppShell>);
    expect(await screen.findByRole("link", { name: "Settlements" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toBeInTheDocument();
  });
});

describe("Admin → Settings", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  const LOCALE = {
    country_code: "IN",
    country_name: "India",
    currency_code: "INR",
    currency_symbol: "₹",
    timezone: "Asia/Kolkata",
    default_language: "en",
    supported_languages: ["en"],
    languages: [{ tag: "en", name: "English", endonym: "English", rtl: false }],
    quantity_unit: "litre",
    quantity_unit_label: "L",
    units: ["litre", "kg"],
    trade_unit: null,
    trade_unit_label: null,
    conversion_factor: null,
    conversion_effective_from: null,
    modules: ["collection", "sales"],
    available_modules: [
      { key: "collection", label: "collects", description: "in" },
      { key: "sales", label: "sells", description: "out" },
    ],
  };

  it("has the two switches, says hiding deletes nothing, and sends the list", async () => {
    const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/auth/session")) return json(session(["collection", "sales"]));
      if (url.endsWith("/v1/organizations/settings/locale") && init?.method === "PUT")
        return json({ ...LOCALE, modules: JSON.parse(String(init.body)).modules });
      if (url.endsWith("/v1/organizations/settings/locale")) return json(LOCALE);
      return json({ title: "not_found" }, 404);
    });
    vi.stubGlobal("fetch", spy);
    const user = userEvent.setup();
    render(<OrganizationSettingsPage />);
    const collects = (await screen.findByTestId("toggle-module-collection")) as HTMLInputElement;
    const sells = screen.getByTestId("toggle-module-sales") as HTMLInputElement;
    expect(collects.checked && sells.checked).toBe(true);
    expect(screen.getByText(/hides its screens from the navigation and nothing else/)).toBeInTheDocument();
    await user.click(collects);
    await waitFor(() =>
      expect(
        spy.mock.calls.some(
          (c) =>
            String(c[0]).endsWith("/v1/organizations/settings/locale") &&
            (c[1] as RequestInit)?.method === "PUT",
        ),
      ).toBe(true),
    );
    const put = spy.mock.calls.find((c) => (c[1] as RequestInit)?.method === "PUT")!;
    expect(JSON.parse(String((put[1] as RequestInit).body))).toEqual({ modules: ["sales"] });
  });

  it("carries the activity log, so an owner without a menu entry for it still has it (WO-104)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/auth/session")) return json(session(["sales"]));
        if (url.endsWith("/v1/organizations/settings/locale"))
          return json({ ...LOCALE, modules: ["sales"] });
        return json({ title: "not_found" }, 404);
      }),
    );
    render(<OrganizationSettingsPage />);
    const link = await screen.findByTestId("settings-activity-log");
    expect(link).toHaveAttribute("href", "/admin/audit");
    expect(link).toHaveTextContent("Open the activity log");
    expect(screen.getByText(/who changed this bill/)).toBeInTheDocument();
  });

  it("will not let the last module be switched off", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/auth/session")) return json(session(["sales"]));
        if (url.endsWith("/v1/organizations/settings/locale"))
          return json({ ...LOCALE, modules: ["sales"] });
        return json({ title: "not_found" }, 404);
      }),
    );
    render(<OrganizationSettingsPage />);
    const sells = (await screen.findByTestId("toggle-module-sales")) as HTMLInputElement;
    expect(sells.checked).toBe(true);
    expect(sells.disabled).toBe(true);
    expect(screen.getByText(/At least one must stay on/)).toBeInTheDocument();
    const section = sells.closest("section")!;
    expect(within(section).getByTestId("toggle-module-collection")).not.toBeChecked();
  });
});
