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

describe("colour everywhere, structurally (LACTEVA-MARKETING-008)", () => {
  it("the atmosphere exists: fixed washes and grain behind every page", () => {
    // "No flat-white viewport anywhere" — the body's backdrop is a fixed
    // pseudo-element carrying at least two radial dairy washes and the
    // SVG grain, so the guarantee is a selector, not a memory.
    const start = css.indexOf("body::before");
    expect(start).toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf("}", start));
    expect(block).toContain("position: fixed");
    expect(block).toContain("feTurbulence");
    expect(block.match(/radial-gradient/g)!.length).toBeGreaterThanOrEqual(2);
  });

  it("the band treatments are defined once each — every band wears the same weather", () => {
    expect(css.match(/^\s*\.lacteva-band-tinted\s*\{/gm)).toHaveLength(1);
    expect(css.match(/^\s*\.lacteva-band-ink\s*\{/gm)).toHaveLength(1);
    // The ink band is the brand's 150° gradient, and its glow is a
    // pseudo-element — light without markup.
    expect(css).toMatch(/\.lacteva-band-ink\s*\{[^}]*linear-gradient\(150deg/);
    expect(css).toContain(".lacteva-band-ink::before");
  });

  it("the card is a gradient hairline over a tinted surface, defined once", () => {
    const definitions = css.match(/^\s*\.lacteva-card\s*\{/gm) ?? [];
    expect(definitions).toHaveLength(1);
    const start = css.indexOf(".lacteva-card {");
    const block = css.slice(start, css.indexOf("}", start));
    // The two-layer background trick: surface in padding-box, hairline
    // gradient in border-box.
    expect(block).toContain("padding-box");
    expect(block).toContain("border-box");
  });

  it("milk numerals clip the gradient to the glyphs", () => {
    const start = css.indexOf(".lacteva-milk-text");
    expect(start).toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf("}", start));
    expect(block).toContain("background-clip: text");
    expect(block).toContain("color: transparent");
  });

  it("the CTA shimmer animates transform only — compositor, no repaint", () => {
    const block = keyframesBlock("cta-shimmer");
    const properties = [...block.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
    expect(properties.length).toBeGreaterThan(0);
    for (const property of properties) {
      expect(["transform", "opacity"]).toContain(property);
    }
    // Slow on purpose: a shimmer under ten seconds is a distraction, not
    // an atmosphere.
    expect(css).toMatch(/animation:\s*cta-shimmer\s*1[0-9]s/);
  });
});
