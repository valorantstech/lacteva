import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The motion rules that must stay true structurally
 * (LACTEVA-MARKETING-004), checked against the stylesheet itself so they
 * are executable rather than remembered.
 */
const css = readFileSync(join(__dirname, "globals.css"), "utf8");

function keyframesBlock(name: string): string {
  const start = css.indexOf(`@keyframes ${name}`);
  expect(start, `@keyframes ${name} exists`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  let depth = 1;
  let i = open + 1;
  while (depth > 0 && i < css.length) {
    if (css[i] === "{") depth += 1;
    if (css[i] === "}") depth -= 1;
    i += 1;
  }
  return css.slice(open + 1, i - 1);
}

describe("marketing motion, structurally", () => {
  it("the settle-in animates opacity and transform only — zero layout shift", () => {
    const block = keyframesBlock("settle-in");
    const properties = [...block.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
    expect(properties.length).toBeGreaterThan(0);
    for (const property of properties) {
      expect(["opacity", "transform"]).toContain(property);
    }
  });

  it("the lift is defined once, and lifts 2px — not 8", () => {
    const definitions = css.match(/^\s*\.lacteva-lift\s*\{/gm) ?? [];
    expect(definitions).toHaveLength(1);
    expect(css).toContain(".lacteva-lift:hover");
    expect(css).toMatch(/\.lacteva-lift:hover\s*\{[^}]*translateY\(-2px\)/);
  });

  it("the settle-in stays inside the motion budget: ≤240ms on the DS curve", () => {
    // The animation runs on --motion-base (240ms) and --ease-out-liquid;
    // pinning the tokens keeps the budget executable.
    expect(css).toMatch(/--motion-base:\s*240ms/);
    expect(css).toMatch(
      /\[data-settle\]\.settle-go\s*>\s*div\s*>\s*\*\s*\{[^}]*var\(--motion-base\)\s+var\(--ease-out-liquid\)/,
    );
  });
});
