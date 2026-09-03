"use client";

/**
 * The collection trend, drawn as inline SVG (DEMO-002).
 *
 * No charting library: the portal ships one dependency-light bundle and a
 * bar-and-line chart over at most ~90 daily points does not justify adding
 * one. More importantly, every charting library wants `number`, and the value
 * series is money — so the rule is drawn explicitly here instead of hidden in
 * a config object:
 *
 *   the numbers used for GEOMETRY are never the numbers used for DISPLAY.
 *
 * Bar heights are computed from `Number(...)`, which is fine and unavoidable —
 * a pixel is a float. Every figure a human reads (axis labels, tooltips, the
 * totals beneath) is rendered by `<Money>` / `<Quantity>` straight from the
 * exact decimal string the platform sent. A rounding error in a bar height is
 * invisible; a rounding error in a total is a wrong statement.
 */

import Link from "next/link";
import { useId, useState } from "react";
import { Money, Quantity } from "@/components/money";
import { unitLabel } from "@/lib/units";
import { EmptyState } from "@/components/states";
import { cn } from "@/lib/utils";

export type TrendDatum = {
  day: string;
  quantity: number;
  /** The exact decimal string from the platform — displayed, never summed. */
  value: string;
  currency: string | null;
  transactions: number;
};

/** Geometry only. See the note above about why this is allowed here. */
const toPlotNumber = (value: string | number): number => {
  const n = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(n) ? n : 0;
};

const shortDay = (iso: string) => {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
};

export function TrendChart({
  data,
  metric,
  unit,
  height = 220,
}: {
  data: TrendDatum[];
  /** Which series is drawn: quantity collected, or what it is worth. */
  metric: "quantity" | "value";
  /** D-21: the unit the platform reported the series in. */
  unit?: string | null;
  height?: number;
}) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  if (data.length === 0) {
    return (
      <EmptyState
        title="No collection in this period"
        description="Choose a wider date range, or open a session at a centre to begin collecting."
      />
    );
  }

  const series = data.map((d) =>
    metric === "quantity" ? d.quantity : toPlotNumber(d.value),
  );
  const peak = Math.max(...series, 0);
  const currency = data.find((d) => d.currency)?.currency ?? null;

  // A flat zero series must not divide by zero, and must not draw full-height
  // bars either: nothing collected should look like nothing collected.
  const scale = (n: number) => (peak > 0 ? (n / peak) * 100 : 0);

  const width = 100;
  const step = data.length > 1 ? width / (data.length - 1) : 0;
  const points = series
    .map((n, i) => `${(i * step).toFixed(3)},${(100 - scale(n)).toFixed(3)}`)
    .join(" ");
  const area = `0,100 ${points} ${width},100`;
  const active = hover === null ? null : data[hover];

  return (
    <div className="flex flex-col gap-3">
      <div className="relative" style={{ height }}>
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="h-full w-full"
          role="img"
          aria-label={
            metric === "quantity"
              ? `Quantity collected per day, peaking at ${peak} ${unitLabel(unit)}`
              : "Collection value per day"
          }
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-success)" stopOpacity="0.14" />
              <stop offset="100%" stopColor="var(--color-success)" stopOpacity="0.01" />
            </linearGradient>
          </defs>
          {/* LACTEVA-ADMIN-015: three lines rather than five, and the two
              above the baseline quieter than it. A grid is scaffolding; the
              eye should find the series, not the ruling. */}
          {[0, 50, 100].map((y) => (
            <line
              key={y}
              x1="0"
              y1={y}
              x2="100"
              y2={y}
              stroke={
                y === 100
                  ? "var(--color-border)"
                  : "color-mix(in oklch, var(--color-border) 45%, transparent)"
              }
              strokeWidth="0.3"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {peak > 0 ? (
            <>
              <polygon points={area} fill={`url(#${gradientId})`} />
              <polyline
                points={points}
                fill="none"
                stroke="var(--color-success)"
                strokeWidth="2.5"
                vectorEffect="non-scaling-stroke"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </>
          ) : null}
        </svg>

        {/*
          The endpoint, emphasised (LACTEVA-ADMIN-015).

          HTML rather than SVG, and not for convenience: this plot is
          `preserveAspectRatio="none"`, so a `<circle>` in it renders as an
          ellipse and a `<text>` renders stretched. Positioning the dot and its
          label over the plot with the same scale arithmetic is the only way to
          draw a round dot and readable words on a chart that must fill
          whatever width it is given.
        */}
        {peak > 0 ? (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            data-testid="trend-endpoint"
          >
            <span
              className="absolute size-[9px] -translate-x-full -translate-y-1/2 rounded-full bg-success"
              style={{ left: "100%", top: `${100 - scale(series[series.length - 1])}%` }}
            />
            <span
              className="absolute -translate-x-full -translate-y-[calc(100%+10px)] whitespace-nowrap text-meta font-semibold text-foreground"
              style={{ left: "100%", top: `${100 - scale(series[series.length - 1])}%` }}
            >
              {metric === "quantity" ? (
                <Quantity value={data[data.length - 1].quantity} unit={unit} />
              ) : (
                <Money
                  amount={data[data.length - 1].value}
                  currency={data[data.length - 1].currency ?? currency}
                />
              )}
            </span>
          </div>
        ) : null}

        {/* One hover target per day, laid over the plot. Buttons rather than
            SVG hit areas so the series is reachable by keyboard. */}
        <div className="absolute inset-0 flex">
          {data.map((d, i) => (
            <button
              key={d.day}
              type="button"
              className={cn(
                "flex-1 border-0 bg-transparent p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                hover === i && "bg-primary/5",
              )}
              aria-label={`${d.day}: ${d.transactions} collections, ${d.quantity} ${unitLabel(unit)}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            />
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 text-xs text-muted-foreground">
        <span>{shortDay(data[0].day)}</span>
        <span aria-live="polite" className="text-center">
          {active ? (
            <span className="text-foreground">
              <span className="font-medium">{active.day}</span> ·{" "}
              {metric === "quantity" ? (
                <Quantity value={active.quantity} unit={unit} />
              ) : (
                <Money amount={active.value} currency={active.currency ?? currency} />
              )}{" "}
              · {active.transactions} collections
            </span>
          ) : (
            <span>hover or tab through a day for detail</span>
          )}
        </span>
        <span>{shortDay(data[data.length - 1].day)}</span>
      </div>
    </div>
  );
}

/**
 * A horizontal breakdown — used for rate bands and centre performance, where
 * the comparison is between a handful of named rows rather than over time.
 */
export function BarBreakdown({
  rows,
  emptyTitle = "Nothing to show",
  emptyDescription,
}: {
  rows: {
    key: string;
    label: string;
    detail?: React.ReactNode;
    magnitude: number;
    /** DEMO-003: where this row leads. Omitted when the page does not exist. */
    href?: string;
  }[];
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  const peak = Math.max(...rows.map((r) => r.magnitude), 0);
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.key} className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            {row.href ? (
              <Link className="truncate font-medium hover:underline" href={row.href}>
                {row.label}
              </Link>
            ) : (
              <span className="truncate font-medium">{row.label}</span>
            )}
            <span className="shrink-0 text-muted-foreground">{row.detail}</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary/70"
              style={{ width: `${peak > 0 ? (row.magnitude / peak) * 100 : 0}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
