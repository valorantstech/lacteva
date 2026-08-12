/**
 * Dates and times, rendered — one definition (DEMO-010).
 *
 * The portal had four. `slice(0, 16)` on most pages, `slice(0, 19)` on the
 * transaction and settlement detail pages, `slice(0, 10)` where only the day
 * matters, and `new Date(...).toLocaleString()` on Operations — which renders
 * in the VIEWER's locale, so the same instant reads `2026-08-12 09:30` on one
 * screen and `8/12/2026, 9:30:00 AM` on the next. During a demonstration that
 * looks like two different systems.
 *
 * The rule is the same one `money.tsx` follows: **format, never compute.** The
 * platform sends ISO-8601 in UTC; these components slice the string rather
 * than parsing it into a `Date`, because parsing and re-rendering would shift
 * the value into the browser's timezone and quietly disagree with the audit
 * trail, the receipt, and the database — for a dairy whose settlement day
 * closes at midnight UTC, that is a row landing on the wrong day.
 *
 * Seconds are deliberately not shown. Nobody reading a delivery or a
 * settlement needs them, and they make a screen read like debug output.
 */

import { cn } from "@/lib/utils";

/** `2026-08-12T09:30:11+00:00` → `2026-08-12 09:30`. */
export function formatStamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const text = String(iso);
  return text.length >= 16 ? `${text.slice(0, 10)} ${text.slice(11, 16)}` : text;
}

/** `2026-08-12T09:30:11+00:00` → `2026-08-12`. */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

export function Stamp({
  value,
  className,
}: {
  value: string | null | undefined;
  className?: string;
}) {
  return <span className={cn("tabular-nums whitespace-nowrap", className)}>{formatStamp(value)}</span>;
}

export function Day({
  value,
  className,
}: {
  value: string | null | undefined;
  className?: string;
}) {
  return <span className={cn("tabular-nums whitespace-nowrap", className)}>{formatDay(value)}</span>;
}
