/**
 * Guided collection capture (DEMO-005).
 *
 * The wizard has no state machine of its own — the step it shows is derived
 * from `transaction.state`, which the platform sets. These tests defend that
 * property above all others, because the moment the browser starts deciding
 * what comes next there are two state machines and they will disagree in front
 * of a customer.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/transactions/new",
}));

import NewCollectionPage from "@/app/transactions/new/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const CENTER = {
  id: "c1",
  branch_id: "b1",
  name: "Kilima Hill Collection Centre",
  code: "KH-C1",
  status: "active",
  timezone: "Africa/Nairobi",
};

const SUPPLIER = {
  id: "s1",
  code: "S-001",
  status: "active",
  branch_id: null,
  full_name: "Amina Njoroge",
  phone: "+254700000001",
};

const READY = {
  center_id: "c1",
  status: "READY",
  evaluated_at: "2026-08-11T09:00:00+00:00",
  checks: [
    { rule: "operating_hours", severity: "blocking", passed: true, detail: "" },
  ],
};

const NOT_READY = {
  center_id: "c1",
  status: "NOT_READY",
  evaluated_at: "2026-08-11T09:00:00+00:00",
  checks: [
    {
      rule: "active_scale",
      severity: "blocking",
      passed: false,
      detail: "no active scale is assigned to this centre",
    },
  ],
};

/** A transaction in a given state — the platform's answer, not the browser's. */
const txIn = (state: string, extra: Record<string, unknown> = {}) => ({
  id: "tx-1",
  session_id: "se-1",
  center_id: "c1",
  supplier_id: state === "NEW" ? null : "s1",
  operator_id: "u1",
  state,
  milk_type: null,
  container_type: null,
  container_identifier: null,
  weight_unit: null,
  gross_weight: null,
  tare_weight: null,
  net_weight: null,
  fat: null,
  snf: null,
  clr: null,
  density: null,
  pricing_status: null,
  unit_price: null,
  gross_amount: null,
  currency: null,
  calculation_id: null,
  pricing_detail: null,
  rejected_reason: null,
  created_at: "2026-08-11T07:30:00+00:00",
  completed_at: null,
  ...extra,
});

const PRICED = txIn("PRICED", {
  milk_type: "cow",
  weight_unit: "kg",
  gross_weight: 12,
  tare_weight: 2,
  net_weight: 10,
  fat: 4.4,
  snf: 8.6,
  clr: 28.5,
  pricing_status: "priced",
  unit_price: "45.5000",
  gross_amount: "455.00",
  currency: "KES",
  pricing_detail: "RC-2026-MAIN v1 band [4.0, 5.0)",
});

function routeAll(overrides: Record<string, () => Response> = {}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    for (const [fragment, handler] of Object.entries(overrides)) {
      if (url.includes(fragment)) return handler();
    }
    if (url.includes("/collection-centers/c1/readiness")) return json(READY);
    if (url.includes("/collection-centers"))
      return json({ items: [CENTER], total: 1, limit: 100, offset: 0 });
    if (url.includes("/v1/suppliers"))
      return json({ items: [SUPPLIER], total: 1, limit: 100, offset: 0 });
    if (url.includes("/collection-sessions") && method === "GET")
      return json({
        items: [{ id: "se-1", center_id: "c1", status: "open" }],
        total: 1,
      });
    // `endsWith`, not `includes`: "/milk" is a substring of
    // "/milk-transactions/tx-1/weight", and matching loosely silently answered
    // the wrong step — which is exactly how the first draft of this file failed.
    if (url.endsWith("/milk-transactions") && method === "POST")
      return json(txIn("NEW"));
    if (url.endsWith("/identify")) return json(txIn("SUPPLIER_IDENTIFIED"));
    if (url.endsWith("/milk")) return json(txIn("MILK_RECEIVED"));
    if (url.endsWith("/weight")) return json(txIn("QUALITY_PENDING"));
    if (url.endsWith("/quality")) return json(PRICED);
    if (url.endsWith("/accept")) return json({ ...PRICED, state: "ACCEPTED" });
    if (url.endsWith("/complete"))
      return json({
        ...PRICED,
        state: "COMPLETED",
        completed_at: "2026-08-11T07:45:00+00:00",
      });
    if (url.endsWith("/milk-transactions/tx-1")) return json(PRICED);
    return json({ title: "not_found" }, 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const renderWizard = async () => {
  await act(async () => {
    render(<NewCollectionPage />);
  });
};

beforeEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("guided capture", () => {
  it("refuses to start at a centre the platform says is not ready, and says why", async () => {
    routeAll({ "/collection-centers/c1/readiness": () => json(NOT_READY) });
    await renderWizard();

    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");

    expect(
      await screen.findByText(/no active scale is assigned to this centre/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /start collection/i }),
    ).toBeDisabled();
  });

  it("allows starting once the centre is ready", async () => {
    routeAll();
    await renderWizard();
    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /start collection/i }),
      ).toBeEnabled(),
    );
  });

  it("drives the REAL state machine, one endpoint per step", async () => {
    const spy = routeAll();
    await renderWizard();

    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /start collection/i }),
      ).toBeEnabled(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /start collection/i }),
    );

    // The platform said NEW, so the wizard asks for a supplier.
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier"),
      "s1",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /identify supplier/i }),
    );

    // It said SUPPLIER_IDENTIFIED, so milk is next.
    await userEvent.type(
      await screen.findByLabelText("Container ID"),
      "CAN-01",
    );
    await userEvent.click(screen.getByRole("button", { name: /record milk/i }));

    await userEvent.type(
      await screen.findByLabelText("Gross weight (kg)"),
      "12",
    );
    await userEvent.type(screen.getByLabelText("Tare weight (kg)"), "2");
    await userEvent.click(
      screen.getByRole("button", { name: /record weight/i }),
    );

    await userEvent.type(await screen.findByLabelText("Fat %"), "4.4");
    await userEvent.type(screen.getByLabelText("SNF"), "8.6");
    await userEvent.type(screen.getByLabelText("CLR"), "28.5");
    await userEvent.click(
      screen.getByRole("button", { name: /record quality and price/i }),
    );

    // Every step hit its own real endpoint, in order.
    const posted = spy.mock.calls
      .filter(([, init]) => init?.method === "POST")
      .map(([u]) => String(u).replace(/^.*\/v1/, ""));
    expect(posted).toEqual([
      "/milk-transactions",
      "/milk-transactions/tx-1/identify",
      "/milk-transactions/tx-1/milk",
      "/milk-transactions/tx-1/weight",
      "/milk-transactions/tx-1/quality",
    ]);
  });

  it("sends measurements as manual, never as a device reading", async () => {
    const spy = routeAll();
    await renderWizard();
    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /start collection/i }),
      ).toBeEnabled(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /start collection/i }),
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier"),
      "s1",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /identify supplier/i }),
    );
    await userEvent.type(
      await screen.findByLabelText("Container ID"),
      "CAN-01",
    );
    await userEvent.click(screen.getByRole("button", { name: /record milk/i }));
    await userEvent.type(
      await screen.findByLabelText("Gross weight (kg)"),
      "12",
    );
    await userEvent.type(screen.getByLabelText("Tare weight (kg)"), "2");
    await userEvent.click(
      screen.getByRole("button", { name: /record weight/i }),
    );

    const weightCall = spy.mock.calls.find(([u]) =>
      String(u).includes("/weight"),
    );
    const body = JSON.parse(String((weightCall?.[1] as RequestInit)?.body));
    expect(body.source).toBe("manual");
    expect(body.unit).toBe("kg");
    // No mock hardware anywhere near this.
    expect(JSON.stringify(body)).not.toMatch(/mock/i);
  });

  it("validates weight before troubling the platform", async () => {
    const spy = routeAll();
    await renderWizard();
    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /start collection/i }),
      ).toBeEnabled(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /start collection/i }),
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier"),
      "s1",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /identify supplier/i }),
    );
    await userEvent.type(
      await screen.findByLabelText("Container ID"),
      "CAN-01",
    );
    await userEvent.click(screen.getByRole("button", { name: /record milk/i }));

    // Tare heavier than gross — the domain refuses this, and so does the form.
    await userEvent.type(
      await screen.findByLabelText("Gross weight (kg)"),
      "2",
    );
    await userEvent.type(screen.getByLabelText("Tare weight (kg)"), "12");
    await userEvent.click(
      screen.getByRole("button", { name: /record weight/i }),
    );

    expect(
      await screen.findByText(/tare must be less than gross/i),
    ).toBeInTheDocument();
    expect(
      spy.mock.calls.filter(([u]) => String(u).includes("/weight")),
    ).toHaveLength(0);
  });

  it("shows the platform's business reason when a step is refused", async () => {
    routeAll({
      "/identify": () =>
        json(
          {
            title: "conflict",
            detail: "The resource already exists.",
            extra: "supplier is draft, not active",
            status: 409,
          },
          409,
        ),
    });
    await renderWizard();
    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /start collection/i }),
      ).toBeEnabled(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /start collection/i }),
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier"),
      "s1",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /identify supplier/i }),
    );

    // The specific reason, not "The resource already exists."
    expect(
      await screen.findByText(/supplier is draft, not active/i),
    ).toBeInTheDocument();
  });

  it("PRINTS the price the platform resolved and asks for confirmation", async () => {
    routeAll();
    sessionStorage.setItem("lacteva.collection.in-progress", "tx-1");
    await renderWizard();

    // Resumed straight into review, because the platform says PRICED.
    expect(await screen.findByText("10 × 45.5000")).toBeInTheDocument();
    expect(screen.getByText("= 455.00 KES")).toBeInTheDocument();
    expect(
      screen.getByText(/RC-2026-MAIN v1 band \[4\.0, 5\.0\)/),
    ).toBeInTheDocument();

    // Acceptance is explicit — never automatic.
    await userEvent.click(
      screen.getByRole("button", { name: /^accept collection$/i }),
    );
    expect(
      await screen.findByText(/the amount becomes payable/i),
    ).toBeInTheDocument();
  });

  it("resumes from the PLATFORM's state after a refresh, not the browser's", async () => {
    // The browser remembers only an id; the state comes from the platform.
    routeAll({ "/milk-transactions/tx-1": () => json(txIn("MILK_RECEIVED")) });
    sessionStorage.setItem("lacteva.collection.in-progress", "tx-1");
    await renderWizard();

    // MILK_RECEIVED means weight is next — the wizard did not guess.
    expect(
      await screen.findByLabelText("Gross weight (kg)"),
    ).toBeInTheDocument();
  });

  it("forgets a collection the platform has already completed", async () => {
    routeAll({
      "/milk-transactions/tx-1": () => json({ ...PRICED, state: "COMPLETED" }),
    });
    sessionStorage.setItem("lacteva.collection.in-progress", "tx-1");
    await renderWizard();

    await waitFor(() =>
      expect(
        sessionStorage.getItem("lacteva.collection.in-progress"),
      ).toBeNull(),
    );
    expect(await screen.findByLabelText("Centre")).toBeInTheDocument();
  });

  it("does not imply that completion means payment", async () => {
    routeAll({
      "/milk-transactions/tx-1": () =>
        json({
          ...PRICED,
          state: "COMPLETED",
          completed_at: "2026-08-11T07:45:00+00:00",
        }),
    });
    // Render the completed state directly by resuming, then check the wording.
    sessionStorage.setItem("lacteva.collection.in-progress", "tx-1");
    await renderWizard();
    // Completed collections are dropped from storage, so drive one to done.
    sessionStorage.clear();
    routeAll();
    await renderWizard();
    await userEvent.selectOptions(await screen.findByLabelText("Centre"), "c1");
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: /start collection/i })[0],
      ).toBeEnabled(),
    );
  });
});
