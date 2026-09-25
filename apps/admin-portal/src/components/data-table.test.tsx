/**
 * The table becomes cards on a phone (WO-96 §1), driven by the same columns.
 */
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type Column, DataTable } from "@/components/data-table";

type Row = { id: string; name: string; due: string; status: string };
const rows: Row[] = [
  { id: "1", name: "Deshmukh household", due: "660.00", status: "issued" },
  { id: "2", name: "Patil household", due: "0.00", status: "paid" },
];
const columns: Column<Row>[] = [
  { key: "name", header: "Customer", role: "title", cell: (r) => r.name },
  { key: "due", header: "Amount due", align: "end", role: "money", cell: (r) => `₹${r.due}` },
  { key: "status", header: "Status", role: "status", cell: (r) => <span>{r.status}</span> },
  { key: "period", header: "Period", secondary: true, cell: () => "Aug 2026" },
  { key: "open", header: "", role: "actions", cell: (r) => <a href={`/invoices/${r.id}`}>Open</a> },
];

/** A phone: `matchMedia` says the narrow query matches. */
function phone(matches = true) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: matches && query.includes("max-width"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("DataTable on a phone", () => {
  it("renders each row as a card: title, money beside it, status, meta, full-width actions", async () => {
    phone();
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} caption="Bills" />);
    const cards = await screen.findAllByTestId("row-card");
    expect(cards).toHaveLength(2);
    expect(screen.queryByRole("table")).toBeNull();
    const first = cards[0];
    expect(within(first).getByText("Deshmukh household")).toBeInTheDocument();
    // The money is in the card — the whole point — and is the large figure.
    const money = first.querySelector('[data-role="money"]')!;
    expect(money.textContent).toContain("₹660.00");
    expect(first.querySelector('[data-role="status"]')!.textContent).toBe("issued");
    // A secondary column is context, and on a card there is room for it.
    expect(first.querySelector('[data-role="meta"]')!.textContent).toContain("Period");
    expect(first.querySelector('[data-role="meta"]')!.textContent).toContain("Aug 2026");
    // The action is at the bottom, not off the right edge.
    expect(within(first.querySelector('[data-role="actions"]') as HTMLElement).getByRole("link", { name: "Open" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Bills" })).toBeInTheDocument();
  });

  it("stays a table when the screen is wide, and where matchMedia does not exist", () => {
    phone(false);
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} caption="Bills" />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByTestId("row-card")).toBeNull();
  });
});
