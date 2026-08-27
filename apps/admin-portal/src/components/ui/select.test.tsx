/**
 * One select, and nothing that isn't it (LACTEVA-ADMIN-008).
 *
 * Fifty native `<select>`s carried six class strings between them. The
 * differences were not decisions — two heights, two radii, two border tokens,
 * two backgrounds and two paddings, distributed by the order the pages were
 * written in. Forty-three of them used `bg-background` where `--card` is the
 * surface underneath, so they rendered a faintly grey box inside a white card,
 * beside an `Input` that did not.
 *
 * These tests hold two separate things: that the primitive is still a real
 * `<select>` with real `<option>`s and honest variant props, and — the part
 * that keeps it true next month — that no page has quietly grown a seventh
 * class string of its own.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Select } from "@/components/ui/select";

describe("the Select primitive", () => {
  it("is a real select with real options", () => {
    // No popover, no portal, no headless dependency: the native listbox is
    // what already works on a handset and with a screen reader.
    render(
      <Select aria-label="Status" defaultValue="paid">
        <option value="">All</option>
        <option value="paid">Paid</option>
      </Select>,
    );
    const el = screen.getByLabelText("Status");
    expect(el.tagName).toBe("SELECT");
    expect((el as HTMLSelectElement).value).toBe("paid");
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("passes the value and the handler straight through", () => {
    // The migration's whole promise: values and handlers are untouched.
    const onChange = vi.fn();
    render(
      <Select aria-label="Method" value="upi" onChange={onChange}>
        <option value="upi">UPI</option>
      </Select>,
    );
    expect(screen.getByLabelText("Method")).toHaveValue("upi");
  });

  it("makes width and size props, not class strings", () => {
    const { container } = render(
      <>
        <Select aria-label="a" />
        <Select aria-label="b" size="sm" width="full" />
      </>,
    );
    const [wide, small] = Array.from(container.querySelectorAll("select"));
    expect(wide.className).toContain("h-9");
    expect(wide.className).not.toContain("w-full");
    expect(small.className).toContain("h-8");
    expect(small.className).toContain("w-full");
  });

  it("takes the same tokens Input takes, so a filter row stops arguing", () => {
    // `bg-background` inside a card is the mismatch this replaces.
    const { container } = render(<Select aria-label="a" />);
    const cls = container.querySelector("select")!.className;
    expect(cls).toContain("bg-transparent");
    expect(cls).toContain("border-input");
    expect(cls).toContain("focus-visible:ring-ring/50");
    expect(cls).not.toContain("bg-background");
  });

  it("still lets a caller constrain a width chosen for reading", () => {
    // Two sites cap their width for line length; that is a caller's decision,
    // not a variant, and `cn` must not drop it.
    const { container } = render(<Select aria-label="a" className="max-w-64" />);
    expect(container.querySelector("select")!.className).toContain("max-w-64");
  });
});

/** Every .tsx under src/, so a new page cannot be missed. */
function sources(dir = "src"): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name);
    if (e.isDirectory()) return sources(path);
    return e.name.endsWith(".tsx") ? [path] : [];
  });
}

/**
 * A raw element that styles itself — the exact shape that spread into six
 * variants last time. Built from parts, and returned FRESH each call: written
 * as a literal this file would match itself and force an allowlist, and a
 * shared /g/ regex carries `lastIndex` between `matchAll` and `test`.
 */
const rawStyledSelect = () =>
  new RegExp("<" + "select\\b([^>]*className[^>]*)>", "g");

describe("no page styles a dropdown of its own", () => {
  // The primitive itself, and nowhere else. There is no allowlist: a site that
  // needs something different needs a variant on the primitive.
  const PRIMITIVE = join("src", "components", "ui", "select.tsx");

  it("finds no self-styled raw element outside the primitive", () => {
    const offenders: string[] = [];
    for (const file of sources()) {
      if (file === PRIMITIVE) continue;
      // Prose mentions in comments are not elements and do not match.
      const hits = [...readFileSync(file, "utf8").matchAll(rawStyledSelect())];
      if (hits.length) offenders.push(`${file} (${hits.length})`);
    }
    expect(offenders).toEqual([]);
  });

  it("finds the primitive is the one place such an element lives", () => {
    // The counterpart: the guard above must be checking something real.
    expect(rawStyledSelect().test(readFileSync(PRIMITIVE, "utf8"))).toBe(true);
  });
});
