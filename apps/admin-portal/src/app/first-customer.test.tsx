/**
 * A new shop can add its first customer (WO-107 · LACTEVA-SALES-005).
 *
 * The New customer form hard-coded the demo seed's product code, so the
 * platform — correctly — refused the first customer in every organisation but
 * the demo's. It now offers the ORGANISATION'S products, follows the chosen
 * product's unit in its labels, prefills the rate from the product's price,
 * says "Add your milk products first" when there is nothing to choose, takes
 * the owner's own word for a customer type, and — on the rounds page — asks
 * for a name, not a code.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/customers",
  useSearchParams: () => new URLSearchParams(),
}));

import CustomersPage from "@/app/customers/page";
import RoutesPage from "@/app/routes/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const SESSION = {
  authenticated: true,
  acting_tenant_id: null,
  tenant_id: "org-1",
  user: { id: "u1", email: "sarwari@patel.example", full_name: "Sarwari Patel", locale: "en", is_active: true },
  organization: { id: "org-1", name: "Patel Dairy Shop and Sweets", currency_code: "INR", timezone: "Asia/Kolkata", modules: ["sales"] },
  roles: [{ name: "tenant-admin", description: "", center_id: null }],
  permissions: ["*"],
};

const product = (code: string, name: string, unit: string, price: string | null) => ({
  id: `pr-${code}`, code, name, unit, default_price: price, currency: "INR", active: true, sort_order: 0,
  created_at: "2026-09-26T00:00:00Z", updated_at: "2026-09-26T00:00:00Z",
});
const COW = product("COW-MILK", "Cow milk", "L", null);
const BUFFALO = product("BUFFALO-MILK", "Buffalo milk", "L", "56.00");
const PANEER = product("PANEER-200-G", "Paneer 200 g", "packet", "90.00");
const OTHER = product("OTHER", "Other shop item", "pc", null);

function stub(products: unknown[], types: string[] = ["household", "Temple"]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.split("?")[0];
      calls.push({ url, init });
      if (path.endsWith("/api/auth/session")) return json(SESSION);
      if (path.endsWith("/v1/products")) return json({ items: products, total: products.length });
      if (path.endsWith("/v1/customers/types")) return json(types);
      if (path.endsWith("/v1/customers") && init?.method === "POST")
        return json({ id: "cu-new", code: "CUS-000001", name: "Flat C-1603" }, 201);
      if (path.endsWith("/v1/customers")) return json({ items: [], total: 0, limit: 15, offset: 0 });
      if (path.endsWith("/v1/routes") && init?.method === "POST")
        return json({ id: "r-new", code: "MORNING-ROUND", name: "Morning round", active: true, notes: "", center_id: null, stops: [] }, 201);
      if (path.endsWith("/v1/drivers") && init?.method === "POST")
        return json({ id: "d-new", code: "RAMESH-PAWAR", full_name: "Ramesh Pawar", phone: "", user_id: null, center_id: null, active: true }, 201);
      // The rounds page's lists are plain arrays.
      if (/\/v1\/(routes|vehicles|drivers|delivery-runs)$/.test(path)) return json([]);
      return json({ items: [], total: 0 });
    }),
  );
  const posted = (suffix: string) =>
    calls
      .filter((c) => c.url.split("?")[0].endsWith(suffix) && c.init?.method === "POST")
      .map((c) => JSON.parse(String(c.init?.body)));
  return { calls, posted };
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());


describe("the New customer form", () => {
  it("offers the organisation's products, follows the unit and prefills the rate", async () => {
    const { posted } = stub([COW, BUFFALO, PANEER, OTHER]);
    render(<CustomersPage />);
    await userEvent.click(await screen.findByRole("button", { name: /New customer/ }));
    const select = (await screen.findByLabelText("Product")) as HTMLSelectElement;
    // OTHER is not a standing order; the three real products are.
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "Cow milk (L)", "Buffalo milk (L)", "Paneer 200 g (packet)",
    ]);
    expect(screen.getByLabelText("Daily quantity (L)")).toBeInTheDocument();
    expect(screen.getByLabelText("Rate per litre")).toBeInTheDocument();
    // Choosing Buffalo milk keeps litres and prefills its price.
    await userEvent.selectOptions(select, "BUFFALO-MILK");
    expect(screen.getByLabelText("Rate per litre")).toHaveValue("56.00");
    // Choosing paneer: the labels follow the product's unit.
    await userEvent.selectOptions(select, "PANEER-200-G");
    expect(screen.getByLabelText("Daily quantity (packet)")).toBeInTheDocument();
    expect(screen.getByLabelText("Rate per packet")).toHaveValue("90.00");
    // Back to buffalo at 0.5 L and ₹56: the body names the product and ITS unit.
    await userEvent.selectOptions(select, "BUFFALO-MILK");
    await userEvent.type(screen.getByLabelText("Name"), "Flat C-1603");
    await userEvent.clear(screen.getByLabelText("Daily quantity (L)"));
    await userEvent.type(screen.getByLabelText("Daily quantity (L)"), "0.500");
    await userEvent.click(screen.getByRole("button", { name: "Register customer" }));
    await waitFor(() => expect(posted("/v1/customers")).toHaveLength(1));
    expect(posted("/v1/customers")[0]).toMatchObject({
      name: "Flat C-1603",
      customer_type: "household",
      plan: { product: "BUFFALO-MILK", default_quantity: "0.500", quantity_unit: "L", unit_price: "56.00" },
    });
    expect(JSON.stringify(posted("/v1/customers")[0])).not.toContain("RAW-COW-MILK");
  });

  it("takes the owner's own word for the type", async () => {
    const { posted } = stub([COW]);
    render(<CustomersPage />);
    await userEvent.click(await screen.findByRole("button", { name: /New customer/ }));
    await screen.findByLabelText("Product");
    await userEvent.selectOptions(screen.getByLabelText("Type", { selector: "#nc-type" }), "__other__");
    await userEvent.type(screen.getByLabelText("Type (your own word)"), "  Temple ");
    await userEvent.type(screen.getByLabelText("Name"), "Shri Ganesh Mandir");
    await userEvent.type(screen.getByLabelText("Rate per litre"), "50");
    await userEvent.click(screen.getByRole("button", { name: "Register customer" }));
    await waitFor(() => expect(posted("/v1/customers")).toHaveLength(1));
    expect(posted("/v1/customers")[0].customer_type).toBe("Temple");
  });

  it("does not pretend when the catalogue has nothing a standing order can be for", async () => {
    const { posted } = stub([OTHER]);
    render(<CustomersPage />);
    await userEvent.click(await screen.findByRole("button", { name: /New customer/ }));
    const note = await screen.findByTestId("no-products");
    expect(note).toHaveTextContent("Add your milk products first");
    expect(within(note).getByRole("link", { name: "Products" })).toHaveAttribute("href", "/admin/products");
    expect(screen.queryByLabelText("Product")).toBeNull();
    expect(screen.getByRole("button", { name: "Register customer" })).toBeDisabled();
    expect(posted("/v1/customers")).toEqual([]);
  });

  it("filters by the types actually in use, from the platform", async () => {
    stub([COW], ["Temple", "hotel", "household"]);
    render(<CustomersPage />);
    const filter = (await screen.findByLabelText("Type", { selector: "#cu-type" })) as HTMLSelectElement;
    await waitFor(() =>
      expect([...filter.options].map((o) => o.textContent)).toEqual(["All types", "Temple", "hotel", "household"]),
    );
  });
});

describe("the rounds page", () => {
  it("creates a round and a driver by name — the code is the platform's to spell", async () => {
    const { posted } = stub([]);
    render(<RoutesPage />);
    await screen.findByText("Add a route");
    await userEvent.type(screen.getByLabelText("Name", { selector: "#Add\\ a\\ route-name" }), "Morning round");
    const routeCard = screen.getByText("Add a route").closest("[data-slot=card]") ?? screen.getByText("Add a route").parentElement!.parentElement!;
    await userEvent.click(within(routeCard as HTMLElement).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(posted("/v1/routes")).toHaveLength(1));
    expect(posted("/v1/routes")[0]).toEqual({ name: "Morning round" });

    await userEvent.type(screen.getByLabelText("Name", { selector: "#Add\\ a\\ driver-full_name" }), "Ramesh Pawar");
    await userEvent.type(screen.getByLabelText(/Code \(optional/, { selector: "#Add\\ a\\ driver-code" }), "DRV-7");
    const driverCard = screen.getByText("Add a driver").closest("[data-slot=card]") ?? screen.getByText("Add a driver").parentElement!.parentElement!;
    await userEvent.click(within(driverCard as HTMLElement).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(posted("/v1/drivers")).toHaveLength(1));
    expect(posted("/v1/drivers")[0]).toEqual({ full_name: "Ramesh Pawar", code: "DRV-7" });
  });
});
