/**
 * Irreversible pricing actions ask first, and the price of milk never rides
 * a float (P1-PORTAL-SCALE-001; audit D-4, D-11).
 *
 * What is pinned:
 *   1. Publish/Archive on a rate card show a consequence-spelling confirm —
 *      cancel sends nothing, confirm sends exactly one call, a double click
 *      cannot send two, and a platform refusal is shown in the platform's
 *      own words with the panel still open for another decision.
 *   2. Deleting a matrix or a price band asks first, naming the thing.
 *   3. A band's unit price is submitted as the operator's own decimal STRING
 *      — trailing zeros intact, no Number() rounding step between what is
 *      displayed and what is sent.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/rate-cards",
  useSearchParams: () => new URLSearchParams(),
}));

import MatricesPage from "@/app/matrices/page";
import RateCardsPage from "@/app/rate-cards/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const problem = (detail: string, status = 409) =>
  new Response(JSON.stringify({ title: "conflict", detail }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });

const card = (over: Record<string, unknown> = {}) => ({
  id: "rc-1",
  code: "RC-2026-MAIN",
  name: "Main cow card",
  description: "",
  currency: "INR",
  effective_from: "2026-08-01",
  effective_until: null,
  status: "approved",
  version: 3,
  branch_id: null,
  created_at: "2026-08-01T00:00:00+00:00",
  updated_at: "2026-08-01T00:00:00+00:00",
  published_at: null,
  archived_at: null,
  ...over,
});

const matrix = (over: Record<string, unknown> = {}) => ({
  id: "mx-1",
  rate_card_id: "rc-1",
  rate_card_code: "RC-2026-MAIN",
  name: "Cow FAT bands",
  product_code: "RAW-COW-MILK",
  product_name: "Cow milk",
  dimension_code: "FAT",
  status: "draft",
  version: 1,
  row_count: 2,
  created_at: "2026-08-01T00:00:00+00:00",
  updated_at: "2026-08-01T00:00:00+00:00",
  ...over,
});

const row = (over: Record<string, unknown> = {}) => ({
  id: "row-1",
  from_value: 3.5,
  to_value: 4.0,
  unit_price: "45.5000",
  active: true,
  ...over,
});

afterEach(() => vi.unstubAllGlobals());

function routeRateCards(
  overrides: Record<string, (url: string, init?: RequestInit) => Response> = {},
) {
  const actions: string[] = [];
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler(url, init);
    }
    if (init?.method === "POST" && /\/v1\/rate-cards\/rc-1\/\w+$/.test(path)) {
      actions.push(path.split("/").pop()!);
      return json(card({ status: "published" }));
    }
    if (path.endsWith("/v1/rate-cards"))
      return json({ items: [card()], total: 1, limit: 20, offset: 0 });
    return json({ items: [], total: 0 });
  });
  vi.stubGlobal("fetch", spy);
  return { actions };
}

describe("rate-card publish/archive discipline", () => {
  it("publish asks first; cancel sends nothing", async () => {
    const { actions } = routeRateCards();
    const user = userEvent.setup();
    render(<RateCardsPage />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    // The consequence, spelled out, naming the card — and nothing sent yet.
    expect(
      screen.getByText(/Publishing RC-2026-MAIN v3 is permanent/),
    ).toBeInTheDocument();
    expect(actions).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Keep it as it is" }));
    expect(screen.queryByText(/Publishing RC-2026-MAIN/)).toBeNull();
    expect(actions).toEqual([]);
  });

  it("confirm sends exactly one call — a double click cannot double it", async () => {
    const { actions } = routeRateCards();
    const user = userEvent.setup();
    render(<RateCardsPage />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    const confirm = screen.getByRole("button", {
      name: "Yes, publish permanently",
    });
    // Two rapid clicks: the second lands on a disabled button.
    await user.dblClick(confirm);
    await waitFor(() => expect(actions).toEqual(["publish"]));
  });

  it("a platform refusal is shown verbatim and the choice stays open", async () => {
    routeRateCards({
      "/v1/rate-cards/rc-1/publish": () =>
        problem("The card has no published matrix for RAW-COW-MILK"),
    });
    const user = userEvent.setup();
    render(<RateCardsPage />);

    await user.click(await screen.findByRole("button", { name: "Publish" }));
    await user.click(
      screen.getByRole("button", { name: "Yes, publish permanently" }),
    );
    expect(
      await screen.findByText(/no published matrix for RAW-COW-MILK/),
    ).toBeInTheDocument();
    // The panel is still there — the operator decides again, or keeps it.
    expect(
      screen.getByRole("button", { name: "Yes, publish permanently" }),
    ).toBeInTheDocument();
  });

  it("archive asks with its own consequence", async () => {
    const { actions } = routeRateCards();
    const user = userEvent.setup();
    render(<RateCardsPage />);

    await user.click(await screen.findByRole("button", { name: "Archive" }));
    expect(
      screen.getByText(/Archiving RC-2026-MAIN v3 takes it out of use/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, archive it" }));
    await waitFor(() => expect(actions).toEqual(["archive"]));
  });
});

function routeMatrices() {
  const bodies: Record<string, unknown>[] = [];
  const deletes: string[] = [];
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.split("?")[0];
    if (init?.method === "DELETE") {
      deletes.push(path);
      return new Response(null, { status: 204 });
    }
    if (init?.method === "POST" && path.endsWith("/v1/pricing-matrices/mx-1/rows")) {
      bodies.push(JSON.parse(String(init.body)));
      return json(row({ id: "row-2" }));
    }
    if (path.endsWith("/v1/pricing-matrices/mx-1"))
      return json({
        matrix: matrix(),
        dimension: { code: "FAT", name: "Fat", unit: "%" },
        rows: [row()],
        gaps: [],
        editable: true,
      });
    if (path.endsWith("/v1/pricing-matrices"))
      return json({ items: [matrix()], total: 1, limit: 20, offset: 0 });
    return json({ items: [], total: 0 });
  });
  vi.stubGlobal("fetch", spy);
  return { bodies, deletes };
}

describe("matrix money and deletion discipline", () => {
  it("a new band's price is sent as the operator's exact decimal string", async () => {
    const { bodies } = routeMatrices();
    const user = userEvent.setup();
    render(<MatricesPage />);

    await user.click(await screen.findByRole("button", { name: "Detail" }));
    await screen.findByLabelText("Unit price");

    await user.type(screen.getByLabelText("From"), "4.0");
    await user.type(screen.getByLabelText("To (excl.)"), "4.5");
    // Trailing zero and four decimals — exactly what a rate chart says.
    await user.type(screen.getByLabelText("Unit price"), "46.5050");
    await user.click(screen.getByRole("button", { name: /Add/ }));

    await waitFor(() => expect(bodies.length).toBe(1));
    // The displayed value IS the submitted value: a string, untouched.
    expect(bodies[0].unit_price).toBe("46.5050");
    expect(typeof bodies[0].unit_price).toBe("string");
  });

  it("deleting a matrix asks first, naming it — cancel deletes nothing", async () => {
    const { deletes } = routeMatrices();
    const user = userEvent.setup();
    render(<MatricesPage />);

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(
      screen.getByText(/Delete the draft matrix “Cow FAT bands”/),
    ).toBeInTheDocument();
    expect(deletes).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Keep it" }));
    expect(deletes).toEqual([]);

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(
      screen.getByRole("button", { name: "Yes, delete the matrix" }),
    );
    await waitFor(() => expect(deletes.length).toBe(1));
  });

  it("deleting a price band asks first with the band's own figures", async () => {
    const { deletes } = routeMatrices();
    const user = userEvent.setup();
    render(<MatricesPage />);

    await user.click(await screen.findByRole("button", { name: "Detail" }));
    // The band row's Delete — inside the detail card.
    const deleteButtons = await screen.findAllByRole("button", {
      name: "Delete",
    });
    await user.click(deleteButtons[deleteButtons.length - 1]);

    expect(
      screen.getByText(/Delete the band 3.5–4 at unit price 45.5000/),
    ).toBeInTheDocument();
    expect(deletes).toEqual([]);
    await user.click(
      screen.getByRole("button", { name: "Yes, delete the band" }),
    );
    await waitFor(() => expect(deletes.length).toBe(1));
    expect(deletes[0].endsWith("/v1/pricing-matrices/mx-1/rows/row-1")).toBe(
      true,
    );
  });
});
