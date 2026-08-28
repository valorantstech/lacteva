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
 * Since LACTEVA-MARKETING-007 the contract also covers the traced LACTEVA
 * wordmark, its colours, and the tagline's wording and placement.
 *
 * If it fails: run `python3 tools/brand/generate.py` and update the inline
 * copy from `mark.json`.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const CONTRACT = JSON.parse(
  readFileSync(join(process.cwd(), "../../tools/brand/mark.json"), "utf8"),
) as {
  path: string;
  can: string;
  dropViewBox: string;
  dairy: string;
  milk: string;
  logo: {
    dairy: string;
    cream: string;
    deep: string;
    navy: string;
    vaTop: string;
    vaBottom: string;
    taglineText: string;
  };
  wordmark: {
    gradient: { axis: string; y0: number; y1: number };
    layers: { navy: string; green: string };
  };
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
    expect(read(file)).toContain(CONTRACT.can);
  });

  it("is drawn from a real path, not a placeholder", () => {
    // A guard against the contract itself going empty and every assertion
    // above passing vacuously.
    for (const path of [
      CONTRACT.path,
      CONTRACT.can,
      CONTRACT.wordmark.layers.navy,
      CONTRACT.wordmark.layers.green,
    ]) {
      expect(path.length).toBeGreaterThan(120);
      expect(path.startsWith("M")).toBe(true);
      expect(path.endsWith("Z")).toBe(true);
    }
  });

  it("keeps the pinned palette", () => {
    expect(CONTRACT.dairy).toBe("#1B5E20");
    expect(CONTRACT.milk).toBe("#FDFBF4");
  });

  it("the lockup carries the traced wordmark, verbatim (LACTEVA-MARKETING-007)", () => {
    // WO-31 Amendment 1: no font-rendered approximation of the wordmark on
    // any committed surface. The letterforms in logo.tsx must be the traced
    // artwork's own outlines and the identity's own colours — a wordmark
    // typed in the UI font would contain neither.
    const source = read("src/components/logo.tsx");
    expect(source).toContain(CONTRACT.wordmark.layers.navy);
    expect(source).toContain(CONTRACT.wordmark.layers.green);
    for (const colour of [
      CONTRACT.logo.navy,
      CONTRACT.logo.vaTop,
      CONTRACT.logo.vaBottom,
      CONTRACT.logo.deep,
      CONTRACT.logo.cream,
    ]) {
      expect(source, `logo.tsx names ${colour}`).toContain(colour);
    }
    // The VA gradient is VERTICAL, in the artwork's own coordinates.
    expect(CONTRACT.wordmark.gradient.axis).toBe("vertical");
    expect(source).toContain(
      `y1="${CONTRACT.wordmark.gradient.y0}"`,
    );
    expect(source).toContain(
      `y2="${CONTRACT.wordmark.gradient.y1}"`,
    );
  });

  it("the tagline is the owner's wording, and lives in exactly two homes", () => {
    // WO-32: "Smart Dairy. Stronger Tomorrow." lands in the footer and the
    // CTA band ONLY. The wording is pinned to the contract, and the ONLY is
    // executable: any other source file that names it fails here.
    const tagline = CONTRACT.logo.taglineText;
    expect(read("src/components/logo.tsx")).toContain(
      `export const TAGLINE = "${tagline}"`,
    );
    const allowed = new Set([
      "src/components/logo.tsx", // the constant itself
      "src/components/site-footer.tsx",
      "src/components/cta-band.tsx",
    ]);
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(join(process.cwd(), dir), {
        withFileTypes: true,
      })) {
        const relative = `${dir}/${entry.name}`;
        if (entry.isDirectory()) walk(relative);
        // Tests assert the tagline; they do not display it.
        else if (
          /\.(ts|tsx|css|svg)$/.test(entry.name) &&
          !/\.test\./.test(entry.name)
        ) {
          if (read(relative).includes(tagline) && !allowed.has(relative)) {
            offenders.push(relative);
          }
        }
      }
    };
    walk("src");
    expect(offenders, "the tagline may not be sprinkled").toEqual([]);
    // And its two homes actually import it rather than re-typing it.
    for (const home of [
      "src/components/site-footer.tsx",
      "src/components/cta-band.tsx",
    ]) {
      expect(read(home)).toContain("TAGLINE");
    }
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
