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
    meniscus: { r: number; width: number; opacity: number };
    body: Array<{ offset: number; color: string }>;
  };
};

const read = (relative: string) =>
  readFileSync(join(process.cwd(), relative), "utf8");

describe("the Lacteva mark", () => {
  it.each([
    ["the lockup", "src/components/logo.tsx"],
    ["the app icon", "src/app/icon.svg"],
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

  it("the rich rendering carries the generated stops (LACTEVA-MARKETING-003)", () => {
    // The vitest half of check_inline.py's RICH_STOPS: the lockup must name
    // the highlight, the meniscus and every body stop from the contract —
    // BRAND-002's half-drift was a silhouette that agreed while the light
    // existed on one surface only.
    const source = read("src/components/logo.tsx");
    const required = [
      String(CONTRACT.rich.highlight.cx),
      String(CONTRACT.rich.highlight.cy),
      String(CONTRACT.rich.meniscus.r),
      ...CONTRACT.rich.body.map((stop) => stop.color),
    ];
    for (const value of required) {
      expect(source, `logo.tsx names ${value}`).toContain(value);
    }
  });
});
