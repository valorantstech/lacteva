"use client";

/**
 * The dashboard's date range (DEMO-002).
 *
 * Presets plus a custom range, resolved to two ISO dates that go to the
 * BACKEND. Nothing here filters data; it only decides which window the server
 * is asked to aggregate over, which is the whole point — the alternative is
 * fetching every transaction and narrowing it in the browser.
 *
 * Dates are computed in UTC because that is the clock the platform stamps a
 * collection with. Using the browser's local day would put "today" an hour or
 * two out for half the world, and a dashboard that disagrees with the receipts
 * is worse than one that shows nothing.
 */

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type RangeKey = "today" | "yesterday" | "7d" | "30d" | "custom";

export type DateRange = { key: RangeKey; from: string; to: string };

const iso = (d: Date) => d.toISOString().slice(0, 10);

function utcToday(): Date {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

function shift(days: number): string {
  const d = utcToday();
  d.setUTCDate(d.getUTCDate() + days);
  return iso(d);
}

export function resolveRange(key: Exclude<RangeKey, "custom">): DateRange {
  const today = iso(utcToday());
  switch (key) {
    case "today":
      return { key, from: today, to: today };
    case "yesterday":
      return { key, from: shift(-1), to: shift(-1) };
    case "7d":
      return { key, from: shift(-6), to: today };
    case "30d":
      return { key, from: shift(-29), to: today };
  }
}

const PRESETS: { key: Exclude<RangeKey, "custom">; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
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
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div
        role="group"
        aria-label="Date range"
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
            onClick={() => onChange(resolveRange(preset.key))}
          >
            {preset.label}
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="sr-only sm:not-sr-only">From</span>
          <input
            type="date"
            aria-label="From date"
            value={value.from}
            max={value.to}
            disabled={busy}
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            onChange={(e) =>
              e.target.value && onChange({ key: "custom", from: e.target.value, to: value.to })
            }
          />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="sr-only sm:not-sr-only">To</span>
          <input
            type="date"
            aria-label="To date"
            value={value.to}
            min={value.from}
            disabled={busy}
            className={cn("h-8 rounded-md border border-input bg-background px-2 text-sm")}
            onChange={(e) =>
              e.target.value && onChange({ key: "custom", from: value.from, to: e.target.value })
            }
          />
        </label>
      </div>
    </div>
  );
}
