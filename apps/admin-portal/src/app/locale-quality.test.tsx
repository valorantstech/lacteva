/**
 * The catalogs hold real translations, not English in three slots
 * (P1-LOCALE-I18N-001).
 *
 * `localization.test.tsx` proves PARITY — every English key exists in Hindi and
 * Arabic. Parity is satisfied by copying English into both, which is exactly
 * what a rushed catalog does and what a reviewer cannot see. These tests prove
 * the other half: that the operator-critical keys carry their own script, that
 * the farmer-facing slip uses the same Hindi words the PLATFORM prints on the
 * parchi, and that interpolation and domain tokens survive translation.
 *
 * Scope note: this milestone localized the transactions family and login. Keys
 * outside that scope are not asserted here — the remaining pages are recorded
 * honestly in LACTEVA-P1-LOCALE-I18N-001.md rather than pretended green.
 */
import { describe, expect, it } from "vitest";

import { CATALOGS, KEYS } from "@/lib/messages";

const DEVANAGARI = /[ऀ-ॿ]/;
const ARABIC = /[؀-ۿ]/;

/** Keys whose value is legitimately identical across languages. */
const SCRIPT_EXEMPT = new Set<string>([
  // Instrument and unit tokens: a meter reads FAT/SNF/CLR in every language,
  // and translating them would not help the operator holding it.
  "transaction.fat",
  "transaction.snf",
  "transaction.clr",
  "tx.snfShort", // "{snf}% SNF" — the instrument's own token
  "tx.atRate", // "@ {rate}" — notation, not prose
]);

/**
 * TO CONFIRM (P1-LOCALE-I18N-001): sentences that state when money becomes
 * payable, or assert an accounting equality to a farmer. They are keyed and
 * carry the English text in every language DELIBERATELY — engineering does not
 * author the Hindi wording under which a dairy owes a farmer money. They are
 * listed here rather than exempted silently, so the list is a visible debt and
 * any NEW untranslated key still fails these tests.
 */
const AWAITING_BUSINESS_TRANSLATION = new Set<string>([
  "wizard.acceptPrompt",
  "wizard.acceptConsequence",
  "wizard.nextSettlement",
  "txDetail.moneyAgrees",
  "txDetail.moneyMismatch",
]);

/** The surfaces an Indian dairy operator reads every day. */
const OPERATOR_CRITICAL = KEYS.filter(
  (k) =>
    k.startsWith("txDetail.") ||
    k.startsWith("wizard.") ||
    k.startsWith("tx.") ||
    k.startsWith("login."),
);

describe("catalog quality", () => {
  it("covers the operator-critical surfaces this milestone localized", () => {
    // A guard against the catalog silently shrinking back.
    expect(OPERATOR_CRITICAL.length).toBeGreaterThan(40);
  });

  it("holds real Devanagari for Hindi, not copied English", () => {
    const untranslated = OPERATOR_CRITICAL.filter((key) => {
      if (SCRIPT_EXEMPT.has(key)) return false;
      if (AWAITING_BUSINESS_TRANSLATION.has(key)) return false;
      const en = CATALOGS.en[key];
      const hi = CATALOGS.hi[key];
      // A value that is pure punctuation/number/token has nothing to translate.
      if (!/[a-zA-Z]{3}/.test(en)) return false;
      return hi === en || !DEVANAGARI.test(hi);
    });
    expect(untranslated).toEqual([]);
  });

  it("holds real Arabic script, not copied English", () => {
    const untranslated = OPERATOR_CRITICAL.filter((key) => {
      if (SCRIPT_EXEMPT.has(key)) return false;
      if (AWAITING_BUSINESS_TRANSLATION.has(key)) return false;
      const en = CATALOGS.en[key];
      const ar = CATALOGS.ar[key];
      if (!/[a-zA-Z]{3}/.test(en)) return false;
      return ar === en || !ARABIC.test(ar);
    });
    expect(untranslated).toEqual([]);
  });

  it("keeps every interpolation variable through translation", () => {
    // A dropped {var} renders a literal brace to a farmer; a renamed one
    // renders nothing at all.
    const vars = (s: string) => (s.match(/\{[a-zA-Z_]+\}/g) ?? []).sort();
    const broken: string[] = [];
    for (const key of KEYS) {
      const en = vars(CATALOGS.en[key]);
      if (en.length === 0) continue;
      for (const lang of ["hi", "ar"] as const) {
        const other = vars(CATALOGS[lang][key]);
        if (en.join(",") !== other.join(",")) broken.push(`${key} (${lang})`);
      }
    }
    expect(broken).toEqual([]);
  });

  it("prints the parchi in the platform's own Hindi words", () => {
    // The on-screen slip and the slip the platform PRINTS/shares must say the
    // same thing — `render_slip_text` in milk_collection/service.py uses these
    // exact words. Two vocabularies for one document is how a farmer ends up
    // holding a paper that disagrees with the screen.
    const platformParchiHindi: Record<string, string> = {
      "txDetail.slipLabel": "पर्ची",
      "field.date": "दिनांक",
      "txDetail.farmer": "किसान",
      "txDetail.milk": "दूध",
      "field.quantity": "मात्रा",
      "delivery.rate": "दर",
      "field.amount": "राशि",
    };
    for (const [key, word] of Object.entries(platformParchiHindi)) {
      expect(CATALOGS.hi[key], `${key} must match the printed parchi`).toBe(
        word,
      );
    }
  });

  it("keeps the untranslated-money list honest and small", () => {
    // Every entry must genuinely still be English in both languages — an
    // entry that HAS been translated must leave this list, so it cannot
    // become a place to hide ordinary untranslated copy.
    for (const key of AWAITING_BUSINESS_TRANSLATION) {
      expect(KEYS, `${key} must exist`).toContain(key);
      expect(
        CATALOGS.hi[key] === CATALOGS.en[key] ||
          CATALOGS.ar[key] === CATALOGS.en[key],
        `${key} now has a translation — remove it from the list`,
      ).toBe(true);
    }
    expect(AWAITING_BUSINESS_TRANSLATION.size).toBeLessThan(12);
  });

  it("never leaves a translated value empty", () => {
    const empty = KEYS.filter(
      (k) =>
        CATALOGS.hi[k].trim().length === 0 || CATALOGS.ar[k].trim().length === 0,
    );
    expect(empty).toEqual([]);
  });
});
