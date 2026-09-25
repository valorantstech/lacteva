/**
 * The Open Graph tags every page actually SERVES (WO-99).
 *
 * Next.js merges metadata shallowly: a page's `openGraph` object REPLACES
 * the layout's, it does not merge into it. So a page that says only
 * `openGraph: { url: "/pricing" }` ships with no og:site_name, no og:type
 * and no og:locale — which is exactly what live served after WO-76, whose
 * guard read the layout's SOURCE and saw `locale: "en_IN"` written there.
 * That was a check of intent, not output. This one resolves each page the
 * way Next does — the page's own object wins outright when present — and
 * asserts what a WhatsApp fetch would read.
 */
/// <reference types="vite/client" />
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import { describe, expect, it, vi } from "vitest";

// The layout loads Google fonts at module scope, which a test cannot; the
// metadata it exports is what is under test.
vi.mock("next/font/google", () => ({
  Geist: () => ({ variable: "", className: "" }),
  Geist_Mono: () => ({ variable: "", className: "" }),
}));

import { metadata as layoutMetadata } from "./layout";

const PAGES = [
  "/",
  "/product",
  "/solutions",
  "/pricing",
  "/company",
  "/request-demo",
  "/start-free-trial",
  "/privacy-policy",
  "/terms",
];

const pageModules = import.meta.glob("./**/page.tsx");

/** Next's rule, applied: the page's `openGraph` replaces the layout's. */
async function resolvedOpenGraph(route: string) {
  const key = `./${route === "/" ? "" : route.slice(1) + "/"}page.tsx`;
  const load = pageModules[key];
  expect(load, `no page module at ${key}`).toBeDefined();
  const mod = (await load()) as { metadata?: Metadata };
  const page = mod.metadata ?? {};
  return (page.openGraph ?? layoutMetadata.openGraph ?? {}) as Record<string, unknown>;
}

describe("what a WhatsApp fetch reads on every page", () => {
  it.each(PAGES)("%s serves og:site_name, og:type, og:locale and its own og:url", async (route) => {
    const og = await resolvedOpenGraph(route);
    expect(og.siteName, `${route} og:site_name`).toBe("Lacteva");
    expect(og.type, `${route} og:type`).toBe("website");
    expect(og.locale, `${route} og:locale`).toBe("en_IN");
    expect(og.url, `${route} og:url`).toBe(route);
    // The image too: a page's object replaces the layout's, and with it the
    // root's file-based image — served on the home page only, until WO-99.
    const images = og.images as unknown[] | undefined;
    expect(images?.length, `${route} og:image`).toBeGreaterThanOrEqual(1);
  });

  it("covers every page the sitemap publishes", () => {
    const found: string[] = [];
    const walk = (dir: string, prefix: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p, `${prefix}/${name}`);
        else if (name === "page.tsx") found.push(prefix || "/");
      }
    };
    walk(__dirname, "");
    // /login is deliberately bare and not in the sitemap; everything else is here.
    for (const route of found.filter((r) => r !== "/login")) expect(PAGES).toContain(route);
  });
});
