/**
 * No screen renders a unit it did not read (D-21 / WO-70).
 *
 * Before this the portal wrote `unit="kg"` in thirty-nine places and ` kg`
 * into template strings in a dozen more, so an Indian dairy's first screen
 * said kilograms over litres. The unit now comes from the record — a
 * transaction's `weight_unit`, an aggregate's `quantity_unit` — or, for the
 * label on an input somebody is about to fill, from the organisation via the
 * locale context. This test greps for the literal so it cannot come back.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { unitLabel } from "@/lib/units";

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(tsx?|ts)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(full);
  }
  return out;
}

describe("units", () => {
  it("turns the platform's word into the symbol a dairy reads", () => {
    expect(unitLabel("litre")).toBe("L");
    expect(unitLabel("kg")).toBe("kg");
    expect(unitLabel("L")).toBe("L");
    // An aggregate across a change of unit says so; the word is shown as sent.
    expect(unitLabel("mixed")).toBe("mixed");
    expect(unitLabel(null)).toBe("");
    expect(unitLabel(undefined)).toBe("");
  });

  it("finds no screen that assumes kilograms", () => {
    const offenders: string[] = [];
    for (const file of walk(join(__dirname, ".."))) {
      if (file.endsWith("messages.ts")) continue; // catalogs carry `{unit}` placeholders
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        if (/unit=\{?"kg"\}?/.test(line) || /\$\{[^}]*\} kg[`" ]/.test(line) || /\/kg\b/.test(line)) {
          offenders.push(`${file.replace(/.*\/src\//, "src/")}:${i + 1}: ${line.trim()}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });
});
