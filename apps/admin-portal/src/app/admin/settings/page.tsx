"use client";

/**
 * Organization settings — country, currency, timezone, languages (DEMO-013 §12).
 *
 * Two different things on one page, deliberately separated because they answer
 * to different people:
 *
 *   THE ORGANIZATION'S settings, which decide what money means and when the
 *   business day begins for everybody. Guarded by
 *   `organization.settings.manage` — DEMO-008's registry, not a new gate.
 *
 *   MY language, which changes nothing for anyone else and needs no permission
 *   at all. Gating a person's own screen behind an administrative grant would
 *   mean filing a ticket to read your own dashboard in Hindi.
 *
 * The country is shown and not editable. Moving an organization between
 * countries changes what its historical money means and which calendar its
 * closed periods were measured in; it is a migration, not a setting.
 */

import { useCallback, useEffect, useState } from "react";

import { AdminPage } from "@/components/admin-page";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  type LocaleSettings,
  can,
  getLocaleSettings,
  getSession,
  type Session,
  setMyLanguage,
  setMyTimezone,
  updateLocaleSettings,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function OrganizationSettingsPage() {
  const t = useT();
  const [settings, setSettings] = useState<LocaleSettings | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [locale, who] = await Promise.all([
        getLocaleSettings(),
        getSession(),
      ]);
      setSettings(locale);
      setSession(who);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("state.unreachable"));
    }
  }, [t]);

  useEffect(() => {
    // Deferred by a tick rather than called inline: React 19's compiler rules
    // (and this portal's lint gate) refuse a setState reached synchronously
    // from an effect body. The same shape every other page here uses.
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const mayManage = can(session, "organization.settings.manage");
  const myLanguage = session?.authenticated ? session.user.locale : "en";
  const myTimezone = session?.authenticated
    ? (session.user.timezone ?? null)
    : null;

  async function chooseMyLanguage(tag: string) {
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      await setMyLanguage(tag);
      // A full navigation, not a router refresh: the language lives in the
      // shell's session state, which every page below reads through the
      // locale provider. Re-fetching here would leave the rail in the old
      // language until something else happened to remount it.
      window.location.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("state.error"));
      setSaving(false);
    }
  }

  async function chooseMyTimezone(timezone: string | null) {
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      await setMyTimezone(timezone);
      setNote(t("settings.saved"));
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("state.error"));
    } finally {
      setSaving(false);
    }
  }

  async function toggleOrganizationLanguage(tag: string, enabled: boolean) {
    if (!settings) return;
    const next = enabled
      ? [...settings.supported_languages, tag]
      : settings.supported_languages.filter((l) => l !== tag);
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      const updated = await updateLocaleSettings({
        supported_languages: next,
        // The platform refuses a default that is not among the supported
        // languages; move it out of the way rather than sending a request it
        // will correctly reject.
        default_language: next.includes(settings.default_language)
          ? settings.default_language
          : next[0],
      });
      setSettings(updated);
      setNote(t("settings.saved"));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("state.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <AdminPage
      title={t("settings.title")}
      description={t("settings.localeHelp")}
      error={error}
      note={note}
    >
      {settings === null ? (
        <p className="text-sm text-muted-foreground">{t("state.loading")}</p>
      ) : (
        <div className="flex flex-col gap-8">
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Fact
              label={t("settings.country")}
              value={settings.country_name}
              hint={settings.country_code}
            />
            <Fact
              label={t("settings.currency")}
              value={`${settings.currency_symbol} ${settings.currency_code}`}
              hint={t("field.currency")}
              testId="org-currency"
            />
            <Fact
              label={t("settings.timezone")}
              value={settings.timezone}
              hint="IANA"
              testId="org-timezone"
            />
            <Fact
              label={t("settings.defaultLanguage")}
              value={settings.default_language}
              hint={t("field.language")}
            />
          </section>

          <p className="text-xs text-muted-foreground">
            {t("settings.countryFixed")}
          </p>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold">
              {t("settings.supportedLanguages")}
            </h2>
            <div className="flex flex-wrap gap-2">
              {settings.languages.map((language) => (
                <span
                  key={language.tag}
                  className="rounded-full border border-border px-3 py-1 text-sm"
                  data-testid={`org-language-${language.tag}`}
                >
                  {language.endonym}
                  <span className="ms-2 text-xs text-muted-foreground">
                    {language.tag}
                  </span>
                </span>
              ))}
            </div>
            {mayManage ? (
              <LanguageToggles
                settings={settings}
                saving={saving}
                onToggle={toggleOrganizationLanguage}
              />
            ) : (
              <p className="text-xs text-muted-foreground">
                {t("state.noPermission")}
              </p>
            )}
          </section>

          <section className="flex flex-col gap-3 border-t border-border pt-6">
            <h2 className="text-sm font-semibold">
              {t("settings.myTimezone")}
            </h2>
            <p className="text-xs text-muted-foreground">
              {t("settings.myTimezoneHelp")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant={myTimezone ? "outline" : "default"}
                disabled={saving}
                onClick={() => chooseMyTimezone(null)}
                data-testid="timezone-inherit"
              >
                {t("settings.useOrganizationTimezone")}
              </Button>
              <span
                className="text-xs text-muted-foreground"
                data-testid="business-timezone"
              >
                {t("settings.businessTimezone")}: {settings.timezone}
              </span>
            </div>
          </section>

          <section className="flex flex-col gap-3 border-t border-border pt-6">
            <h2 className="text-sm font-semibold">
              {t("settings.myLanguage")}
            </h2>
            <p className="text-xs text-muted-foreground">
              {t("settings.myLanguageHelp")}
            </p>
            <div className="flex flex-wrap gap-2">
              {settings.languages.map((language) => (
                <Button
                  key={language.tag}
                  type="button"
                  variant={language.tag === myLanguage ? "default" : "outline"}
                  disabled={saving}
                  onClick={() => chooseMyLanguage(language.tag)}
                  data-testid={`choose-language-${language.tag}`}
                >
                  {language.endonym}
                </Button>
              ))}
            </div>
          </section>
        </div>
      )}
    </AdminPage>
  );
}

function Fact({
  label,
  value,
  hint,
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  testId?: string;
}) {
  return (
    <div className="rounded-lg border border-border p-4" data-testid={testId}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <p className="mt-1 text-lg font-semibold">{value}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/**
 * Switching a language on or off for the whole organization.
 *
 * Only languages the ORGANIZATION'S COUNTRY offers are listed: the platform
 * refuses anything else, and offering a control that leads to a refusal is the
 * kind of broken promise the navigation rules already forbid.
 */
function LanguageToggles({
  settings,
  saving,
  onToggle,
}: {
  settings: LocaleSettings;
  saving: boolean;
  onToggle: (tag: string, enabled: boolean) => void;
}) {
  const t = useT();
  const enabled = new Set(settings.supported_languages);
  return (
    <div className="flex flex-wrap gap-2">
      {settings.languages.map((language) => (
        <Button
          key={`toggle-${language.tag}`}
          type="button"
          size="sm"
          variant="outline"
          disabled={saving || (enabled.size === 1 && enabled.has(language.tag))}
          onClick={() => onToggle(language.tag, !enabled.has(language.tag))}
          data-testid={`toggle-language-${language.tag}`}
        >
          {enabled.has(language.tag)
            ? `− ${language.name}`
            : `+ ${language.name}`}
        </Button>
      ))}
      <span className="self-center text-xs text-muted-foreground">
        {t("settings.supportedLanguages")}
      </span>
    </div>
  );
}
