/**
 * The CSV import flow (P0-PILOT-003).
 *
 * The rules under test are the honesty rules: the preview shows exactly what
 * was parsed (quoted commas included) and names rows missing the required
 * column BEFORE anything is sent; the request carries the rows as parsed —
 * plans nested, centre codes split — never repaired; and the server's per-row
 * verdicts (including the duplicate-naming error) are rendered verbatim.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/customers/import",
}));

import CustomerImportPage from "@/app/customers/import/page";
import SupplierImportPage from "@/app/suppliers/import/page";
import { parseCsv } from "@/components/csv-import";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => vi.unstubAllGlobals());

describe("the CSV parser", () => {
  it("keeps quoted commas and quotes intact", () => {
    const rows = parseCsv('name,address\n"Sharma, General Stores","Shop ""4"", APMC Road"\n');
    expect(rows).toEqual([
      ["name", "address"],
      ['Sharma, General Stores', 'Shop "4", APMC Road'],
    ]);
  });
});

describe("customer import page", () => {
  it("previews parsed rows and flags the one missing its name — before sending", async () => {
    render(<CustomerImportPage />);
    const box = screen.getByLabelText("CSV content");
    await userEvent.click(box);
    await userEvent.paste(
      "name,phone,plan_product,plan_quantity,plan_unit,plan_price\n" +
        "Hotel Annapurna,+91 98450 00111,RAW-COW-MILK,45,L,56.50\n" +
        ",+91 98450 00222,RAW-COW-MILK,10,L,58.00\n",
    );

    expect(await screen.findByText(/Preview — 2 rows/)).toBeInTheDocument();
    expect(screen.getByText(/missing “name”/)).toBeInTheDocument();
    expect(screen.getByText("Hotel Annapurna")).toBeInTheDocument();
  });

  it("sends the rows as parsed — plan nested — and renders per-row verdicts verbatim", async () => {
    const spy = vi.fn(async () =>
      json([
        { row: 0, status: "created", customer_id: "c1", code: "CUS-2026-000001" },
        {
          row: 1,
          status: "error",
          error: "duplicate of existing customer CUS-2026-000009 (Café Madhuban)",
        },
      ]),
    );
    vi.stubGlobal("fetch", spy);

    render(<CustomerImportPage />);
    await userEvent.click(screen.getByLabelText("CSV content"));
    await userEvent.paste(
      "name,phone,plan_product,plan_quantity,plan_unit,plan_price\n" +
        "Hotel Annapurna,+91 98450 00111,RAW-COW-MILK,45,L,56.50\n" +
        "Café Madhuban,+91 98450 00333,,,,\n",
    );
    await userEvent.click(await screen.findByRole("button", { name: /import 2 rows/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String(spy.mock.calls[0][1]?.body));
    expect(body.rows[0].plan).toEqual({
      product: "RAW-COW-MILK",
      default_quantity: "45",
      quantity_unit: "L",
      unit_price: "56.50",
    });
    expect(body.rows[1].plan).toBeUndefined();

    expect(await screen.findByText(/1 created, 1 failed/)).toBeInTheDocument();
    expect(
      screen.getByText(/duplicate of existing customer CUS-2026-000009/),
    ).toBeInTheDocument();
    expect(screen.getByText(/created CUS-2026-000001/)).toBeInTheDocument();
  });
});

describe("supplier import page", () => {
  it("splits centre codes and posts to the supplier endpoint", async () => {
    const spy = vi.fn(async () => json([{ row: 0, status: "created", supplier_id: "s1" }]));
    vi.stubGlobal("fetch", spy);

    render(<SupplierImportPage />);
    await userEvent.click(screen.getByLabelText("CSV content"));
    await userEvent.paste(
      "code,full_name,phone,village,center_codes\n" +
        "S-001,Ramesh Patil,+91 98220 00111,Wagholi,KH-C1;LR-C1\n",
    );
    await userEvent.click(await screen.findByRole("button", { name: /import 1 rows/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toContain("/v1/suppliers/import");
    const body = JSON.parse(String(init?.body));
    expect(body.rows[0].center_codes).toEqual(["KH-C1", "LR-C1"]);
    expect(body.rows[0].full_name).toBe("Ramesh Patil");
  });
});
