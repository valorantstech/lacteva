"use client";

/**
 * Translation for the admin portal (DEMO-013 §6).
 *
 * **No framework.** react-intl, next-intl and lingui all solve problems this
 * portal does not have — locale-routed URLs, plural rule engines, ICU message
 * compilation, translator round-trips — and each would add a build step and a
 * dependency to render a few hundred short strings. The work order asks for a
 * clean maintainable mechanism and warns against unnecessary frameworks; this
 * is a dictionary, a context and a hook.
 *
 * **The rule that matters more than the mechanism:** a translated string is
 * looked up by KEY. There is no `if (country === "India")` anywhere in this
 * portal, and adding Arabic is a new column in the catalog rather than a new
 * branch in a component.
 *
 * **Where the language comes from.** The signed-in session, which carries the
 * user's own choice (`user.locale`) and the organization's default. Never the
 * browser: `navigator.language` is a device setting, and a shared machine in a
 * dairy office would flip a supervisor's screen because of what the last
 * person's laptop was configured to.
 *
 * Missing keys fall back to English and then to the key itself — an English
 * sentence is something a person can act on, and a visible key is something an
 * engineer can grep for. Neither is a blank screen.
 */

import { createContext, useCallback, useContext, useMemo } from "react";

import { CATALOGS, type Catalog } from "./messages";

/** `hi-IN` → `hi`. Catalogs are per language; the region carries money and time. */
export function baseLanguage(tag: string | null | undefined): string {
  return (tag ?? "en").split("-")[0].toLowerCase();
}

export type Translate = (key: string, vars?: Record<string, string | number>) => string;

type LocaleContextValue = {
  /** The full BCP-47 tag in force, e.g. `hi-IN`. */
  locale: string;
  /** The catalog key, e.g. `hi`. */
  language: string;
  /** The organization's currency, for anything that renders money. */
  currency: string | null;
  /** The organization's IANA zone, for anything that renders a date. */
  timezone: string | null;
  t: Translate;
};

const FALLBACK: LocaleContextValue = {
  locale: "en",
  language: "en",
  currency: null,
  timezone: null,
  t: (key) => CATALOGS.en[key] ?? key,
};

const LocaleContext = createContext<LocaleContextValue>(FALLBACK);

/** `{count} customers` → `12 customers`. Deliberately not a plural engine:
 *  every string in this catalog is written to read correctly either way. */
function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    name in vars ? String(vars[name]) : whole,
  );
}

/**
 * A translator without the context.
 *
 * The shell itself renders the provider, so it cannot consume it — and the
 * navigation is exactly the text that must be translated. Same catalog, same
 * fallback, no second implementation.
 */
export function translatorFor(locale: string | null | undefined): Translate {
  const catalog: Catalog = CATALOGS[baseLanguage(locale)] ?? CATALOGS.en;
  return (key, vars) => interpolate(catalog[key] ?? CATALOGS.en[key] ?? key, vars);
}

export function LocaleProvider({
  locale,
  currency,
  timezone,
  children,
}: {
  locale: string | null | undefined;
  currency?: string | null;
  timezone?: string | null;
  children: React.ReactNode;
}) {
  const language = baseLanguage(locale);
  const catalog: Catalog = CATALOGS[language] ?? CATALOGS.en;

  const t = useCallback<Translate>(
    (key, vars) => interpolate(catalog[key] ?? CATALOGS.en[key] ?? key, vars),
    [catalog],
  );

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale: locale ?? "en",
      language,
      currency: currency ?? null,
      timezone: timezone ?? null,
      t,
    }),
    [locale, language, currency, timezone, t],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

/** Everything a screen needs to speak to this person about this organization. */
export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}

/** The common case: just the translator. */
export function useT(): Translate {
  return useContext(LocaleContext).t;
}
