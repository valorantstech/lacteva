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
    // WO-39 retired the portal's login reveal, which left BRAND-003's rich
    // rendering with no consumer here, and WO-38 deleted it. The lit drop
    // still ships where it is still drawn — the marketing site's nav reveal —
    // and `check_inline.py` plus that app's own suite guard it there.
    ["the auth lockup", "src/components/lockup.tsx"],
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
  // The portal no longer DRAWS the rich mark — WO-39 retired the reveal that
  // did, and WO-38 removed the orphan. What survives here is the half that is
  // still this app's business: that the shared contract still carries the
  // block, so a surface that starts drawing it again has numbers to draw
  // from. The rendering itself is asserted where it is rendered.
  it("the contract carries a rich block at all", () => {
    // A guard against every assertion above passing vacuously against an
    // empty object.
    expect(CONTRACT.rich.glow.r).toBeGreaterThan(0);
    expect(CONTRACT.rich.meniscus.opacity).toBeGreaterThan(0);
    expect(CONTRACT.rich.meniscus.opacity).toBeLessThan(1);
  });
});
