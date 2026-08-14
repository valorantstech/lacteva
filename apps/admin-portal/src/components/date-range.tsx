"use client";

/**
 * The dashboard's date range (DEMO-002, corrected in DEMO-015).
 *
 * Presets plus a custom range, resolved to two ISO dates that go to the
 * BACKEND. Nothing here filters data; it only decides which window the server
 * is asked to aggregate over, which is the whole point — the alternative is
 * fetching every transaction and narrowing it in the browser.
 *
 * **"Today" is the DAIRY's today**, and this file used to compute it in UTC.
 * That was defensible when every tenant was Kenyan — Nairobi is UTC+3, so the
 * two agree for all but three hours of the night — and it is wrong for India.
 * Bengaluru is UTC+5:30: between midnight and 05:30 IST the UTC date is still
 * yesterday, so a manager opening the delivery report before dawn asked for
 * the previous day's round and got it, labelled "Today". A rider on the
 * morning round would have found the screen empty.
 *
 * The organization's zone comes from the locale context, which already carries
 * it for every other date on the platform. `Intl` resolves the local calendar
 * date without shipping a timezone database — it is the one the browser
 * already has. With no zone in context this falls back to UTC, which is what
 * the server does too (`FALLBACK_TIMEZONE`), so the two never disagree about
 * what a missing setting means.
 */

import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type RangeKey = "today" | "yesterday" | "7d" | "30d" | "custom";

export type DateRange = { key: RangeKey; from: string; to: string };

/** The calendar date it is *right now* in a given IANA zone.
 *
 * Exported because it is the platform's rule, not this component's: DEMO-019
 * found the reports screen defaulting its window with
 * `new Date().toISOString()`, which is UTC, so a Kenyan dairy after local
 * midnight opened its collection report on yesterday. One helper means the
 * next screen cannot get it wrong in a new way.
 */
export function todayIn(timezone: string | null): string {
  // `en-CA` formats as YYYY-MM-DD, which is the ISO date the API wants.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone ?? "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

/** `days` before that date, on the calendar rather than the clock. */
function shift(timezone: string | null, days: number): string {
  const [y, m, d] = todayIn(timezone).split("-").map(Number);
  // Built at UTC noon so that adding whole days can never land on the wrong
  // side of a DST boundary — the arithmetic is calendar arithmetic, and none
  // of it should depend on how long a particular day happened to be.
  const anchor = new Date(Date.UTC(y, m - 1, d, 12));
  anchor.setUTCDate(anchor.getUTCDate() + days);
  return anchor.toISOString().slice(0, 10);
}

export function resolveRange(
  key: Exclude<RangeKey, "custom">,
  timezone: string | null = null,
): DateRange {
  const today = todayIn(timezone);
  switch (key) {
    case "today":
      return { key, from: today, to: today };
    case "yesterday":
      return { key, from: shift(timezone, -1), to: shift(timezone, -1) };
    case "7d":
      return { key, from: shift(timezone, -6), to: today };
    case "30d":
      return { key, from: shift(timezone, -29), to: today };
  }
}

const PRESETS: { key: Exclude<RangeKey, "custom">; messageKey: string }[] = [
  { key: "today", messageKey: "range.today" },
  { key: "yesterday", messageKey: "range.yesterday" },
  { key: "7d", messageKey: "range.last_7_days" },
  { key: "30d", messageKey: "range.last_30_days" },
];

export function DateRangePicker({
  value,
  onChange,
  busy,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
  busy?: boolean;
}) {
  const { t, timezone } = useLocale();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div
        role="group"
        aria-label={t("range.label")}
        className="flex flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-1"
      >
        {PRESETS.map((preset) => (
          <Button
            key={preset.key}
            type="button"
            size="sm"
            variant={value.key === preset.key ? "secondary" : "ghost"}
            aria-pressed={value.key === preset.key}
            disabled={busy}
            onClick={() => onChange(resolveRange(preset.key, timezone))}
          >
            {t(preset.messageKey)}
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="sr-only sm:not-sr-only">{t("range.from")}</span>
          <input
            type="date"
            aria-label={t("range.from")}
            value={value.from}
            max={value.to}
            disabled={busy}
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            onChange={(e) =>
              e.target.value &&
              onChange({ key: "custom", from: e.target.value, to: value.to })
            }
          />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="sr-only sm:not-sr-only">{t("range.to")}</span>
          <input
            type="date"
            aria-label={t("range.to")}
            value={value.to}
            min={value.from}
            disabled={busy}
            className={cn(
              "h-8 rounded-md border border-input bg-background px-2 text-sm",
            )}
            onChange={(e) =>
              e.target.value &&
              onChange({ key: "custom", from: value.from, to: e.target.value })
            }
          />
        </label>
      </div>
    </div>
  );
}
