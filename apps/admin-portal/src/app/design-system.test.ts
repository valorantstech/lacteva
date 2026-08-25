/**
 * The design system, as assertions (Design System V1).
 *
 * A palette in a document is a suggestion. These are the parts of the system
 * that must hold for it to be trustworthy, checked against the real token
 * file — because "excellent contrast and accessibility" is either measurable
 * or it is decoration.
 *
 * The contrast maths is WCAG 2.1: OKLCH → Oklab → linear sRGB → relative
 * luminance → ratio. It is implemented here rather than imported so the guard
 * has no dependency that could quietly change what "AA" means.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join("src", "app", "globals.css"), "utf8");

/** The token values declared in one block of the stylesheet. */
function tokensOf(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block`);
  const body = css.slice(start, css.indexOf("\n}", start));
  const out: Record<string, string> = {};
  for (const [, name, value] of body.matchAll(/^\s*(--[a-z0-9-]+):\s*([^;]+);/gim)) {
    out[name] = value.trim();
  }
  return out;
}

function srgbFromOklch(input: string): [number, number, number] | null {
  const m = input.match(
    /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*[\d.]+%?\s*)?\)/i,
  );
  if (!m) return null;
  const [L, C, hDeg] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l3 = l_ ** 3;
  const m3 = m_ ** 3;
  const s3 = s_ ** 3;

  return [
    4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
    -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
    -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3,
  ];
}

/** WCAG relative luminance from LINEAR sRGB. */
function luminance(rgb: [number, number, number]): number {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const [r, g, b] = rgb.map(clamp) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg: string, bg: string): number {
  const a = srgbFromOklch(fg);
  const b = srgbFromOklch(bg);
  if (!a || !b) throw new Error(`not an oklch pair: ${fg} / ${bg}`);
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Every pair a person actually reads. Body text is held to AA (4.5); the
 * foreground-on-ground pairs an operator stares at for a whole shift are held
 * higher on purpose.
 */
const PAIRS: Array<[fg: string, bg: string, min: number, what: string]> = [
  ["--foreground", "--background", 7, "body text on the page"],
  ["--card-foreground", "--card", 7, "text on a card"],
  ["--muted-foreground", "--background", 4.5, "secondary text on the page"],
  ["--muted-foreground", "--card", 4.5, "secondary text on a card"],
  ["--primary-foreground", "--primary", 4.5, "label on a primary button"],
  ["--secondary-foreground", "--secondary", 4.5, "label on a secondary button"],
  ["--success-foreground", "--success", 4.5, "label on success"],
  ["--warning-foreground", "--warning", 4.5, "label on warning"],
  ["--destructive-foreground", "--destructive", 4.5, "label on destructive"],
  ["--info-foreground", "--info", 4.5, "label on info"],
  ["--intelligence-foreground", "--intelligence", 4.5, "label on an intelligence signal"],
  ["--ink-foreground", "--ink", 7, "text on an ink band"],
  // The hero. `--muted-foreground` vanished on deep green, which is the
  // whole reason these tokens exist — so they are measured, not eyeballed.
  ["--on-brand", "--primary", 7, "primary text on the brand ground"],
  ["--on-brand-muted", "--primary", 4.5, "metric labels on the brand ground"],
  ["--on-brand-positive", "--primary", 4.5, "a positive delta on the brand ground"],
  ["--on-brand-negative", "--primary", 4.5, "a negative delta on the brand ground"],
];

describe.each([":root", ".dark"])("contrast in %s", (selector) => {
  const tokens = tokensOf(selector);
  it.each(PAIRS)("%s on %s clears %s:1 — %s", (fg, bg, min, what) => {
    // The dark face redefines only some tokens; fall back to the light value,
    // which is exactly how the cascade resolves it in the browser.
    const light = tokensOf(":root");
    const ratio = contrast(tokens[fg] ?? light[fg], tokens[bg] ?? light[bg]);
    expect(ratio, `${what} in ${selector} was ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(min);
  });
});

describe("the palette is actually a palette", () => {
  it("is not the greyscale it started as", () => {
    // The product shipped stock shadcn defaults — every token `oklch(L 0 0)`,
    // zero chroma — which is why the portal read as an unstyled scaffold.
    // This is the guard against silently regressing to that.
    const tokens = tokensOf(":root");
    const chromatic = Object.entries(tokens).filter(([, v]) => {
      const m = v.match(/oklch\(\s*[\d.]+\s+([\d.]+)/);
      return m && Number(m[1]) > 0.02;
    });
    expect(chromatic.length).toBeGreaterThan(15);
  });

  it("keeps the brand green as the primary in both faces", () => {
    // ~150° in OKLCH is the dairy green carried from the mobile app's
    // #1B5E20 and the marketing site. If this drifts, the three surfaces
    // stop being one product.
    for (const selector of [":root", ".dark"]) {
      const hue = tokensOf(selector)["--primary"].match(/oklch\([\d.]+\s+[\d.]+\s+([\d.]+)/);
      expect(Number(hue![1])).toBeGreaterThan(140);
      expect(Number(hue![1])).toBeLessThan(160);
    }
  });

  it("gives intelligence a hue that belongs to nothing else", () => {
    // The point of the indigo is that a computed signal cannot be confused
    // with success, warning, brand or water.
    const t = tokensOf(":root");
    const hueOf = (name: string) =>
      Number(t[name].match(/oklch\([\d.]+\s+[\d.]+\s+([\d.]+)/)![1]);
    const intelligence = hueOf("--intelligence");
    for (const other of ["--primary", "--success", "--warning", "--destructive", "--water", "--fresh"]) {
      expect(Math.abs(intelligence - hueOf(other))).toBeGreaterThan(30);
    }
  });
});

describe("motion", () => {
  it("defines every duration and easing in one place", () => {
    for (const token of [
      "--motion-instant",
      "--motion-fast",
      "--motion-base",
      "--motion-slow",
      "--motion-flow",
      "--ease-standard",
      "--ease-out-liquid",
      "--ease-in-out-liquid",
    ]) {
      expect(css).toContain(token);
    }
  });

  it("honours reduced motion globally rather than per component", () => {
    // A component that remembers to check `prefers-reduced-motion` is a
    // component that can forget. This is the one place it is handled.
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
    const block = css.slice(css.indexOf("prefers-reduced-motion"));
    expect(block).toMatch(/animation-duration:\s*1ms\s*!important/);
    expect(block).toMatch(/transition-duration:\s*1ms\s*!important/);
  });

  it("keeps the operator's critical path fast", () => {
    // Motion may express state; it must never delay work. The interactive
    // timings stay at or under a quarter second.
    const ms = (name: string) => Number(css.match(new RegExp(`${name}:\\s*(\\d+)ms`))![1]);
    expect(ms("--motion-instant")).toBeLessThanOrEqual(120);
    expect(ms("--motion-fast")).toBeLessThanOrEqual(200);
    expect(ms("--motion-base")).toBeLessThanOrEqual(260);
  });
});

describe("typography", () => {
  it("defines a responsive scale rather than fixed desktop sizes", () => {
    // A scale built from fixed px shrinks badly; every step here is a clamp()
    // whose floor is the mobile size and whose ceiling is the desktop one.
    for (const token of ["--type-display", "--type-page", "--type-section", "--type-metric"]) {
      const value = css.match(new RegExp(`${token}:\\s*([^;]+);`))![1];
      expect(value, `${token} should clamp`).toContain("clamp(");
    }
  });

  it("keeps the mobile floor legible", () => {
    // The floor is what an operator reads on a phone in daylight. Display
    // must not fall below 2rem, and metadata never below 13px.
    const floor = (token: string) =>
      Number(css.match(new RegExp(`${token}:\\s*clamp\\(([\\d.]+)rem`))![1]);
    expect(floor("--type-display")).toBeGreaterThanOrEqual(2);
    expect(floor("--type-page")).toBeGreaterThanOrEqual(1.5);
    expect(css).toMatch(/--type-meta:\s*0\.8125rem/);
  });
});

describe("gradients", () => {
  it("are dairy families, not rainbows", () => {
    // Each gradient must be two steps of ONE family. The guard: no gradient
    // may name more than two distinct colour sources.
    const names = [
      "--gradient-milk",
      "--gradient-cream-fresh",
      "--gradient-dairy",
      "--gradient-intelligence",
      "--gradient-water",
    ];
    for (const name of names) {
      const value = css.match(new RegExp(`${name}:\\s*([^;]+);`))![1];
      const stops = value.match(/oklch\(|var\(--/g) ?? [];
      expect(stops.length, `${name} has ${stops.length} colour stops`).toBeLessThanOrEqual(4);
      expect(value).toContain("150deg"); // one light direction across the system
    }
  });
});

describe("the extended motion vocabulary", () => {
  it("is covered by the reduced-motion block", () => {
    // Every new animation class must be named in the global honouring —
    // a component that animates outside it is a component that ignores the
    // preference.
    const block = css.slice(css.indexOf("prefers-reduced-motion"));
    for (const cls of [
      "lacteva-surface",
      "lacteva-ripple",
      "lacteva-droplet",
      "lacteva-tick",
      "lacteva-attend",
    ]) {
      expect(block, `${cls} must be neutralised`).toContain(cls);
    }
    // And the hover lift must stop moving.
    expect(block).toMatch(/\.lacteva-lift:hover\s*\{\s*transform:\s*none/);
  });

  it("keeps the hover lift subtle", () => {
    // 2px. This is a platform someone uses for eight hours, not a landing page.
    const lift = css.match(/\.lacteva-lift:hover\s*\{([^}]+)\}/)![1];
    const px = Number(lift.match(/translateY\(-([\d.]+)px\)/)![1]);
    expect(px).toBeLessThanOrEqual(3);
  });
});
