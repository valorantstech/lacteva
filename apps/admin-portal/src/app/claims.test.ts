import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Claim discipline for the portal, as an executable check rather than prose —
 * the marketing site's claims.test.ts pattern, extended to product UI
 * (P0-PRODUCT-VISIBILITY-002).
 *
 * The capability-visibility audit (LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT)
 * found ZERO overclaims in this tree — honesty held by inspection. This test
 * makes it hold by construction: copy that asserts an unavailable capability
 * (AI beyond the statistical deviation flag, GPS, SAP, SSO, automated
 * scale/analyzer capture, QR scanning, WhatsApp/SMS sending, forecasting,
 * federation, farmer app, web outlet portal, compliance attestations) fails
 * the suite before it ships.
 *
 * Two tiers, because honesty has two shapes here:
 *  - FORBIDDEN: claim shapes that cannot be honest anywhere today.
 *  - ROADMAP_ONLY: vocabulary that IS legitimate — but only on the roadmap
 *    page, where every item is explicitly labelled Coming soon / Enterprise /
 *    Future and rendered inert (see roadmap-page.test.tsx). Anywhere else in
 *    the portal, naming these capabilities reads as having them.
 *
 * Deliberately NOT banned: the honest anti-claims this tree already carries —
 * "nothing here pretends a device supplied a value", "not that WhatsApp will
 * reach it", "does not try to predict that" — and factual features that share
 * a noun with a future one (the supplier QR is really RENDERED today; only
 * scanning is future).
 */

const ROADMAP_DIR = join("app", "roadmap");

const FORBIDDEN: Array<{ pattern: RegExp; why: string }> = [
  // -- AI: the only intelligence shipped is a statistical deviation flag.
  { pattern: /(?<!before )AI-powered/i, why: "no ML is deployed; the deviation flag is statistics" },
  { pattern: /powered by (AI|artificial intelligence)/i, why: "no ML is deployed" },
  { pattern: /machine[- ]learning (predicts|detects|powers|drives)/i, why: "no ML is deployed" },
  { pattern: /predicti(ve|on)/i, why: "nothing predicts; anomaly/forecasting are roadmap items" },
  // -- Location: no GPS/location code exists anywhere in the product.
  { pattern: /\bGPS\b/, why: "no GPS exists and it is never a pilot dependency" },
  { pattern: /location track|geofenc/i, why: "no location tracking exists" },
  // -- Hardware: capture is manual-first; mock readings are refused in prod.
  { pattern: /automatically (reads?|captures?|weighs?|measures?)/i, why: "capture is manual; automated read-assist is discovery-gated roadmap" },
  { pattern: /(scale|analyzer) (is )?(connected|integrated|online)/i, why: "no device integration is shipped" },
  { pattern: /reads? the (scale|analyzer)/i, why: "no device integration is shipped" },
  { pattern: /\bIoT\b/i, why: "no IoT capability exists" },
  // -- QR: the supplier QR is rendered (real); scanning it is roadmap.
  { pattern: /scan (a|the|your) (QR|code|barcode)|tap to scan/i, why: "QR scanning is not built; only rendering a QR is real" },
  // -- Messaging: templates and registry are real; no BSP/DLT provider is
  //    contracted, so nothing can promise a send.
  { pattern: /WhatsApp (is )?(connected|enabled|live)\b/i, why: "no messaging provider is contracted" },
  { pattern: /(sent|delivered) (via|over|by) (WhatsApp|SMS)/i, why: "no messaging provider is contracted; nothing is sent today" },
  // -- Government / compliance: documents, not integrations; no attestations.
  { pattern: /government (integration|portal|filing|approved)/i, why: "no government integration exists" },
  { pattern: /SOC ?2|ISO[- ]?(?!8601|4217)\d{4,5}|GDPR|HIPAA|PCI[- ]DSS/i, why: "no certifications or compliance attestations exist to claim (ISO 8601 dates and ISO 4217 currency codes are factual standards, not attestations)" },
  { pattern: /(legally|fully) compliant|100% secure|absolutely secure/i, why: "no compliance or absolute-security claims" },
];

const ROADMAP_ONLY: Array<{ pattern: RegExp; why: string }> = [
  { pattern: /\bAI\b/, why: "AI may be named only where it is labelled not-built (the roadmap page)" },
  { pattern: /machine[- ]learning/i, why: "ML exists only as a labelled roadmap item" },
  { pattern: /artificial intelligence/i, why: "AI exists only as a labelled roadmap item" },
  { pattern: /\bSAP\b/, why: "SAP/ERP integration is ENTERPRISE roadmap — no vendor, no protocol" },
  { pattern: /\bSSO\b|single sign-?on/i, why: "enterprise SSO is ENTERPRISE roadmap, not built" },
  { pattern: /federat(ion|ed)/i, why: "federation/org-to-org is ENTERPRISE roadmap, not built" },
  { pattern: /global identity/i, why: "global identity is ENTERPRISE roadmap, not built" },
  { pattern: /\bforecast/i, why: "forecasting is a V2 roadmap item, not built" },
  { pattern: /farmer app/i, why: "there is no farmer app; farmers are records who receive a parchi" },
  { pattern: /outlet portal/i, why: "the web outlet portal is a future option, not built" },
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
  const root = join(__dirname, "..");
  const files = collectSourceFiles(root);

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

  for (const { pattern, why } of ROADMAP_ONLY) {
    it(`says ${pattern} only on the labelled roadmap page (${why})`, () => {
      const offenders = files.filter(
        (file) =>
          !relative(root, file).startsWith(ROADMAP_DIR) &&
          pattern.test(readFileSync(file, "utf8")),
      );
      expect(offenders).toEqual([]);
    });
  }
});
