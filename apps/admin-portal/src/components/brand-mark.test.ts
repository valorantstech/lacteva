/**
 * The mark on this surface is still THE mark (LACTEVA-BRAND-002; D-2).
 *
 * The Lacteva drop existed three times in this repository — the marketing
 * component, the marketing app icon, and the portal shell — with three
 * different geometries, three viewBoxes, and a "highlight" that appeared on
 * one of them. Nothing failed, because nothing was checking. One mark drawn
 * three times is three marks.
 *
 * Every surface now derives from `tools/brand/mark.py`, which writes
 * `tools/brand/mark.json` as the contract. This test reads that contract and
 * asserts the inline copy in this app has not drifted from it — no import
 * across apps, no Python at test time, just the same string on both sides.
 *
 * If it fails: run `python3 tools/brand/generate.py` and update the inline
 * copy from `mark.json`.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const CONTRACT = JSON.parse(
  readFileSync(join(process.cwd(), "../../tools/brand/mark.json"), "utf8"),
) as {
  path: string;
  dropViewBox: string;
  dairy: string;
  milk: string;
  rich: {
    highlight: { cx: number; cy: number; rx: number; ry: number };
    meniscus: { x1: number; y1: number; r: number; width: number; opacity: number };
    body: { offset: number; color: string }[];
    bodyAxis: { x1: number; y1: number; x2: number; y2: number };
    glow: { cx: number; cy: number; r: number };
  };
};

const read = (relative: string) =>
  readFileSync(join(process.cwd(), relative), "utf8");

describe("the Lacteva mark", () => {
  it.each([
    ["the app shell", "src/components/app-shell.tsx"],
    // LACTEVA-BRAND-003: the rich rendering is the SAME outline, lit. A
    // surface that drew the enriched mark from its own numbers would be the
    // BRAND-002 defect wearing better clothes.
    ["the rich mark", "src/components/brand-mark.tsx"],
  ] as const)("%s carries the generated geometry", (_label, file) => {
    expect(read(file)).toContain(CONTRACT.path);
  });

  it("is drawn from a real path, not a placeholder", () => {
    // A guard against the contract itself going empty and every assertion
    // above passing vacuously.
    expect(CONTRACT.path.length).toBeGreaterThan(120);
    expect(CONTRACT.path.startsWith("M")).toBe(true);
    expect(CONTRACT.path.endsWith("Z")).toBe(true);
  });

  it("keeps the pinned palette", () => {
    expect(CONTRACT.dairy).toBe("#1B5E20");
    expect(CONTRACT.milk).toBe("#FDFBF4");
  });
});

describe("the rich rendering (LACTEVA-BRAND-003)", () => {
  const source = read("src/components/brand-mark.tsx");

  it("carries the LIGHT, not only the silhouette", () => {
    // BRAND-002 found a mark whose outline agreed across three surfaces while
    // its highlight existed on exactly one of them. Checking the path alone
    // would let that happen again one layer up.
    const { highlight, meniscus } = CONTRACT.rich;
    for (const value of [highlight.cx, highlight.cy, highlight.rx, highlight.ry]) {
      expect(source).toContain(String(value));
    }
    expect(source).toContain(String(meniscus.r));
    expect(source).toContain(String(meniscus.width));
  });

  it("carries every body stop, in the board's order", () => {
    const stops = CONTRACT.rich.body;
    expect(stops).toHaveLength(3);
    // Milk into a cream shadow, with a lit edge — depth from light, not from
    // an effect.
    expect(stops[0].color).toBe("#FFFFFF");
    expect(stops[1].color).toBe(CONTRACT.milk);
    expect(stops[2].color).toBe("#E4DEC9");
    for (const stop of stops) expect(source).toContain(stop.color);
  });

  it("clips the meniscus to the drop", () => {
    // Mapped faithfully from the board the arc runs a little past the bulb.
    // Unclipped, that is a green whisker hanging off the mark.
    expect(source).toContain("clipPath");
    expect(source).toContain('clipPath="url(#lacteva-drop)"');
  });

  it("the contract carries a rich block at all", () => {
    // A guard against every assertion above passing vacuously against an
    // empty object.
    expect(CONTRACT.rich.glow.r).toBeGreaterThan(0);
    expect(CONTRACT.rich.meniscus.opacity).toBeGreaterThan(0);
    expect(CONTRACT.rich.meniscus.opacity).toBeLessThan(1);
  });
});
