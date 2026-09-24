/**
 * The words that change with the modules — and only the words that are
 * wrong (D-31 · WO-85 §6).
 *
 * A milk shop has one "collection centre", its own premises, and the phrase
 * is meaningless to its owner. For an organisation that runs `sales` and NOT
 * `collection`, a SMALL set of keys reads differently; every key without an
 * override falls through to the catalogue. An organisation that does both
 * has a collection centre and keeps every existing word.
 *
 * Kept deliberately small and in one place: this is not a per-profile
 * translation system, and the next word somebody wants to change goes here
 * or nowhere.
 */
import type { Catalog } from "@/lib/messages";

export const SALES_ONLY_OVERRIDES: Record<string, Partial<Catalog>> = {
  en: {
    "entity.center": "Shop",
    "dashboard.heroTitle": "The shop, this morning",
    "dashboard.salesDetail": "Milk delivered to customers, and what they owe the shop",
    "shell.notYourAreaDetail":
      "Your role does not include this part of the shop. Everything you do have access to is in the navigation — nothing here is broken.",
  },
  hi: {
    "entity.center": "दुकान",
    "dashboard.heroTitle": "आज सुबह की दुकान",
    "dashboard.salesDetail": "ग्राहकों को दिया गया दूध, और वे दुकान को क्या देते हैं",
    "shell.notYourAreaDetail":
      "आपकी भूमिका में दुकान का यह हिस्सा शामिल नहीं है। जो कुछ आपकी पहुँच में है वह नेविगेशन में है — यहाँ कुछ भी टूटा नहीं है।",
  },
};

/** The overrides for a language, or none. `en-IN` → `en`. */
export function overridesFor(language: string, salesOnly: boolean): Partial<Catalog> {
  if (!salesOnly) return {};
  return SALES_ONLY_OVERRIDES[language] ?? SALES_ONLY_OVERRIDES.en ?? {};
}
