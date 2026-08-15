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
  // MKT-004B owner decisions: pricing philosophy and data-ownership
  // commitments are ON HOLD until commercial pricing/legal is final.
  { pattern: /farmers never pay/i, why: "pricing philosophy is held until pricing is finalized" },
  { pattern: /per-seat|seat-based|seat tax/i, why: "pricing philosophy is held until pricing is finalized" },
  { pattern: /sold or brokered|shared or sold|never sold/i, why: "data-ownership commitment is a pending commercial/legal decision" },
  // Unsupported capabilities: not shipped, so not marketable.
  { pattern: /certified integration|hardware freedom/i, why: "no hardware certification program exists" },
  { pattern: /\bSSO\b|single sign-on|API gateway|on-prem/i, why: "enterprise capabilities that are not built yet" },
  // Generic forbidden marketing shapes (owner directive #10).
  { pattern: /bank-grade|military-grade/i, why: "generic security claims without evidence" },
  { pattern: /(#1|number one|the only|leading|best) (dairy|platform|software|provider|solution)/i, why: "no superlative market-position claims" },
  { pattern: /\d+\s*%\s*(fewer|less|more|faster|increase|reduction|saving)/i, why: "no invented ROI statistics" },
  // MKT-004C: the trial is a request flow fulfilled by a person — the
  // copy must never promise self-service provisioning that does not exist.
  { pattern: /no credit card|instant access|start instantly|account (is )?created instantly|sign up instantly/i, why: "trial provisioning is manual; no instant-access promises" },
  // MKT-004E: commercial terms that are not finalized cannot be promised.
  { pattern: /cancel anytime|no setup fee|money-?back/i, why: "commercial terms are not finalized" },
  { pattern: /unlimited (users|operators|centres|centers|suppliers|customers)/i, why: "no plan limits exist to waive; pricing is not finalized" },
  { pattern: /\d+\s*%\s*(off|discount)|free forever/i, why: "no discounts or free tiers exist" },
  // MKT-004F: superlatives and certifications that do not exist.
  { pattern: /world'?s (first|largest|best|leading)|largest dairy/i, why: "no market-position superlatives" },
  { pattern: /\bguaranteed\b/i, why: "no guarantees are commercially defined" },
  { pattern: /SOC ?2|ISO ?\d{4,5}|GDPR|HIPAA|PCI[- ]DSS/i, why: "no certifications or compliance attestations exist to claim" },
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
