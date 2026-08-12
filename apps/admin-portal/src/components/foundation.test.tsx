/**
 * The shared UI foundation (DEMO-001).
 *
 * The money tests are the ones that matter. Everything else here is polish;
 * `formatAmount` is the boundary where exact decimal arithmetic from the
 * platform meets JavaScript, and the whole point of the component is that it
 * never crosses into `Number`. These assertions would fail loudly the day
 * somebody "simplifies" it with `parseFloat(...).toFixed(2)`.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DataTable } from "@/components/data-table";
import { Money, Quantity, formatAmount } from "@/components/money";
import { EmptyState, ErrorState } from "@/components/states";
import { StatusBadge, statusLabel, statusVariant } from "@/components/status-badge";

describe("money", () => {
  it("groups thousands without touching the decimals it was given", () => {
    expect(formatAmount("5647.50")).toBe("5,647.50");
    expect(formatAmount("1800.00")).toBe("1,800.00");
    expect(formatAmount("999.99")).toBe("999.99");
    expect(formatAmount("1234567.89")).toBe("1,234,567.89");
  });

  it("preserves trailing zeros and four-decimal unit prices exactly", () => {
    // 45.0000 is a UNIT PRICE: the platform stores Numeric(12,4) and the zeros
    // are significant. A float round-trip would render this "45".
    expect(formatAmount("45.0000")).toBe("45.0000");
    expect(formatAmount("40.000")).toBe("40.000");
    expect(formatAmount("0.10")).toBe("0.10");
  });

  it("does not lose precision a float would", () => {
    // 0.1 + 0.2 !== 0.3 in binary floating point. The platform sends the exact
    // string; this component must hand it back unharmed.
    expect(formatAmount("0.30")).toBe("0.30");
    expect(formatAmount("9007199254740993.01")).toBe("9,007,199,254,740,993.01");
  });

  it("handles negatives, absent values and anything that is not a number", () => {
    expect(formatAmount("-1250.75")).toBe("-1,250.75");
    expect(formatAmount(null)).toBe("—");
    expect(formatAmount(undefined)).toBe("—");
    expect(formatAmount("")).toBe("—");
    expect(formatAmount("n/a")).toBe("n/a");
  });

  it("renders the currency beside the amount, and omits it when there is none", () => {
    const { rerender } = render(<Money amount="5647.50" currency="KES" />);
    expect(screen.getByText("5,647.50")).toBeInTheDocument();
    expect(screen.getByText("KES")).toBeInTheDocument();

    rerender(<Money amount={null} currency="KES" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("KES")).not.toBeInTheDocument();
  });

  it("renders a quantity with its unit", () => {
    render(<Quantity value="40.000" unit="kg" />);
    expect(screen.getByText("40.000")).toBeInTheDocument();
    expect(screen.getByText("kg")).toBeInTheDocument();
  });
});

describe("status", () => {
  it("maps each lifecycle word to a consistent tone", () => {
    expect(statusVariant("completed")).toBe("default");
    expect(statusVariant("finalized")).toBe("default");
    expect(statusVariant("failed")).toBe("destructive");
    expect(statusVariant("rejected")).toBe("destructive");
    expect(statusVariant("archived")).toBe("outline");
    expect(statusVariant("pending")).toBe("secondary");
  });

  it("never lets colour be the only signal — the word is always rendered", () => {
    render(<StatusBadge status="QUALITY_PENDING" />);
    expect(screen.getByText("quality pending")).toBeInTheDocument();
  });

  it("says 'unknown' rather than rendering an empty badge", () => {
    expect(statusLabel(null)).toBe("unknown");
    expect(statusLabel("")).toBe("unknown");
  });
});

describe("data table", () => {
  const columns = [
    { key: "name", header: "Name", cell: (r: { name: string }) => r.name },
  ];

  it("shows an empty state that says what to do next, not just 'no data'", () => {
    render(
      <DataTable
        caption="Suppliers"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.name}
        empty={{ title: "No suppliers yet", description: "Add one to begin collecting." }}
      />,
    );
    expect(screen.getByText("No suppliers yet")).toBeInTheDocument();
    expect(screen.getByText("Add one to begin collecting.")).toBeInTheDocument();
  });

  it("announces an error as an alert and offers a retry", async () => {
    const onRetry = vi.fn();
    render(
      <DataTable
        caption="Suppliers"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.name}
        error="The platform is unreachable."
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("The platform is unreachable.");
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("renders rows with an accessible caption describing the table", () => {
    render(
      <DataTable
        caption="Suppliers in this organization"
        columns={columns}
        rows={[{ name: "Amina Njoroge" }]}
        rowKey={(r) => r.name}
      />,
    );
    expect(screen.getByText("Amina Njoroge")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /suppliers in this organization/i })).toBeInTheDocument();
  });

  it("reports the range it is showing, so a page is never mistaken for the whole", () => {
    render(
      <DataTable
        caption="Suppliers"
        columns={columns}
        rows={[{ name: "Amina Njoroge" }]}
        rowKey={(r) => r.name}
        page={{ offset: 10, limit: 10, total: 27, onChange: vi.fn() }}
      />,
    );
    const status = screen.getByText(/Showing/);
    expect(status).toHaveTextContent("11");
    expect(status).toHaveTextContent("20");
    expect(status).toHaveTextContent("27");
  });
});

describe("states", () => {
  it("gives an error the alert role so it is not silent to a screen reader", () => {
    render(<ErrorState message="Something went wrong." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });

  it("renders an empty state with its guidance", () => {
    render(<EmptyState title="Nothing today" description="Open a session to begin." />);
    expect(screen.getByText("Nothing today")).toBeInTheDocument();
    expect(screen.getByText("Open a session to begin.")).toBeInTheDocument();
  });
});

// --- one definition of how money looks (DEMO-010) ----------------------------
//
// Two screens were found in a browser printing `13860.00 KES` and
// `1176.00 KES` while every other screen printed `13,860.00 KES`. Both had
// grown their own formatter. During a demonstration that reads as two
// different systems, and no reviewer catches it by reading a diff.
//
// So the rule is asserted rather than remembered: `money.tsx` is the only
// place that decides how an exact decimal is displayed.

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return name.endsWith(".tsx") && !name.includes(".test.") ? [path] : [];
  });
}

describe("money is formatted in exactly one place", () => {
  it("no page defines its own amount formatter", () => {
    const offenders = sourceFiles("src/app")
      .filter((path) => {
        const source = readFileSync(path, "utf8");
        // A local helper is fine if it delegates; it is not fine if it
        // stringifies the amount itself.
        return /^const (money|amount|fmt\w*)\s*=[^\n]*\$\{String\(/m.test(source);
      })
      .map((path) => path.replace("src/app/", ""));
    expect(offenders).toEqual([]);
  });

  it("groups thousands, and keeps the platform's decimals exactly", () => {
    expect(formatAmount("13860.00")).toBe("13,860.00");
    expect(formatAmount("1176.50")).toBe("1,176.50");
    expect(formatAmount("353234.00")).toBe("353,234.00");
    // Trailing zeros are significant — they state the scale.
    expect(formatAmount("40.000")).toBe("40.000");
  });
});
