import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Claim discipline, as an executable check rather than prose — the same
 * pattern as the admin portal's foundation.test.tsx.
 *
 * The workspace's own rules bind the copy: "Marketing describes what
 * exists" (Master/Marketing charter), and Product Principles rule out
 * "claiming intelligence the platform does not have" — no ML is deployed
 * today. There are also no customers yet, so testimonials and traction
 * numbers cannot exist honestly.
 */

const FORBIDDEN: Array<{ pattern: RegExp; why: string }> = [
  // "AI-ready before AI-powered" is the one approved use of the phrase —
  // it is the disclaimer itself, so the lookbehind lets exactly it through.
  { pattern: /(?<!before )AI-powered/i, why: "no ML is deployed; the honest line is 'AI-ready before AI-powered'" },
  { pattern: /powered by (AI|artificial intelligence)/i, why: "no ML is deployed" },
  { pattern: /machine learning (predicts|detects|powers)/i, why: "no ML is deployed" },
  { pattern: /trusted by \d/i, why: "there are no customers to count yet" },
  { pattern: /testimonial/i, why: "there are no customers to quote yet" },
  { pattern: /asChild/, why: "this design system is Base UI, which has no asChild" },
];

function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      files.push(...collectSourceFiles(path));
    } else if (/\.(ts|tsx)$/.test(entry) && !entry.includes(".test.")) {
      files.push(path);
    }
  }
  return files;
}

describe("claim discipline", () => {
  const files = collectSourceFiles(join(__dirname, ".."));

  it("finds the source tree", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  for (const { pattern, why } of FORBIDDEN) {
    it(`never says ${pattern} (${why})`, () => {
      const offenders = files.filter((file) =>
        pattern.test(readFileSync(file, "utf8")),
      );
      expect(offenders).toEqual([]);
    });
  }
});
