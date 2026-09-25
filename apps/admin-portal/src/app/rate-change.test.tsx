/**
 * The bulk rate change (WO-89 §5): previewed, then applied in one request.
 *
 *  * Preview asks the platform with `preview: true` and shows who would
 *    change (with the old rate) and who is skipped and why — and nothing else
 *    is sent until the owner confirms;
 *  * Apply sends the same command with `preview: false` and shows the result;
 *  * the card says deliveries already recorded keep their own rate.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/customers",
  useSearchParams: () => new URLSearchParams(),
}));

import { RateChangeCard } from "@/components/rate-change";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const answer = (preview: boolean) => ({
  preview,
  product: "COW-MILK",
  unit_price: "64.0000",
  effective_from: "2026-09-01",
  changed: [
    { customer_id: "cu-1", code: "H-001", name: "Tower 1-2006", old_rate: "60.0000" },
    { customer_id: "cu-2", code: "H-002", name: "A-1607", old_rate: "60.0000" },
  ],
  skipped: [{ customer_id: "cu-3", code: "H-003", name: "Paused", old_rate: "60.0000", reason: "plan is paused on the effective date" }],
});

function stub() {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.includes("/api/auth/session"))
      return json({ authenticated: true, organization: { timezone: "Asia/Kolkata" }, permissions: ["*"] });
    if (path.includes("/v1/products")) return json({ items: [{ code: "COW-MILK", name: "Cow milk" }], total: 1 });
    if (path.endsWith("/v1/customers/rate-change") && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as { preview?: boolean };
      return json(answer(body.preview === true));
    }
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("Change rate", () => {
  it("previews before anything moves, then applies the same command", async () => {
    const spy = stub();
    const user = userEvent.setup();
    render(<RateChangeCard onClose={() => {}} />);
    const card = await screen.findByTestId("rate-change-card");
    expect(within(card).getByText(/keeps the rate it was recorded at/)).toBeInTheDocument();
    await waitFor(() => expect(within(card).getByRole("option", { name: "Cow milk" })).toBeInTheDocument());
    await user.selectOptions(within(card).getByLabelText("Product"), "COW-MILK");
    await user.type(within(card).getByLabelText("New rate"), "64");
    await user.click(within(card).getByRole("button", { name: "Preview" }));

    const preview = await within(card).findByTestId("rate-change-preview");
    expect(preview.textContent).toContain("Would change 2 plan(s) to 64.0000");
    expect(within(preview).getByText(/H-001 · Tower 1-2006 — was 60.0000/)).toBeInTheDocument();
    expect(within(card).getByTestId("rate-change-skipped").textContent).toContain("plan is paused");
    const posts = () =>
      spy.mock.calls.filter((c) => String(c[0]).endsWith("/v1/customers/rate-change"));
    expect(posts()).toHaveLength(1);
    expect(JSON.parse(String((posts()[0][1] as RequestInit).body))).toMatchObject({
      product: "COW-MILK",
      unit_price: "64",
      customer_ids: null,
      preview: true,
    });

    await user.click(within(card).getByRole("button", { name: "Apply to 2 plan(s)" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(JSON.parse(String((posts()[1][1] as RequestInit).body))).toMatchObject({
      product: "COW-MILK",
      unit_price: "64",
      preview: false,
    });
    expect((await within(card).findByTestId("rate-change-preview")).textContent).toContain("Changed 2 plan(s)");
    expect(within(card).queryByRole("button", { name: /Apply to/ })).toBeNull();
  });
});
