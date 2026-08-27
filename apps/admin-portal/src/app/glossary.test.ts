/**
 * One word per concept, made executable (LACTEVA-ADMIN-005; decision D-4).
 *
 * The terminology audit found the migration half-done rather than absent,
 * which is the worse state: fifteen catalog values said "centre" and one said
 * "Centers"; the billing family said Bill, Bills, Billed and Billing in the
 * same breath. Nobody was wrong on purpose. There was simply nothing checking,
 * so every new string picked whichever dialect its author had last read — and
 * a customer demo reads as assembled rather than designed.
 *
 * So the glossary is a test now. It reads the EN catalog only: Hindi and
 * Arabic spell neither word in Latin script, and translating is a separate
 * judgement (a household may keep its natural word for an invoice — the
 * architect's ruling on A4).
 *
 * Keys are never checked, because a key is a code identifier: `nav.centers`
 * and `billing.title` are addresses, not copy, and renaming them would break
 * every caller for no reader's benefit.
 */
import { describe, expect, it } from "vitest";

import { CATALOGS } from "@/lib/messages";

const en = CATALOGS.en;

/** Interpolation variables are not prose — `{center}` is a caller's contract. */
const visible = (value: string) => value.replace(/\{[^}]*\}/g, " ");

/**
 * The only survivors of "Bill", by ruling B2: "Billing" names the ACTIVITY and
 * the section, not the document, and "Invoicing" reads worse for both. There
 * is deliberately no "billable" entry — ruling B1 put state words under the
 * document noun, so "invoiceable" is the word and "billable" is not allowed
 * back in through an allowlist.
 */
const ALLOWED = [/\bBilling\b/g, /\bbilling period\b/gi];

const withoutAllowed = (value: string) =>
  ALLOWED.reduce((text, pattern) => text.replace(pattern, " "), value);

const offenders = (pattern: RegExp, allow = false) =>
  Object.entries(en)
    .filter(([key]) => !(allow && key.startsWith("billing.")))
    .map(([key, value]) => [key, allow ? withoutAllowed(visible(value)) : visible(value)])
    .filter(([, text]) => pattern.test(text as string))
    .map(([key]) => key);

describe("the D-4 glossary, in the EN catalog", () => {
  it("spells it Centre, never Center", () => {
    // en-IN, and the word a dairy in Karnataka reads on a sign.
    expect(offenders(/\bcenters?\b/i)).toEqual([]);
  });

  it("says Invoice, never Bill", () => {
    // "Billing" and "billing period" survive by ruling B2; the document, the
    // plural and the state word do not.
    expect(offenders(/\bbills?\b|\bbilled\b|\bbillable\b/i, true)).toEqual([]);
  });

  it("is actually reading a populated catalog", () => {
    // Without this the two assertions above pass beautifully against nothing.
    expect(Object.keys(en).length).toBeGreaterThan(400);
    expect(en["entity.invoice"]).toBe("Invoice");
    expect(en["nav.centers"]).toBe("Centres");
  });

  it("keeps the allowlisted activity name", () => {
    // The guard must not be so eager that it forces "Invoicing" on a section
    // that is correctly called Billing.
    expect(en["billing.title"]).toBe("Billing");
    expect(en["nav.billing"]).toBe("Billing");
  });
});
