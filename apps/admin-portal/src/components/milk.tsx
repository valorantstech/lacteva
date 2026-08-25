"use client";

/**
 * The milk primitives (Design System V1.1).
 *
 * The first pass had one small progress bar, which read as a generic widget.
 * These are the reusable pieces that make a Lacteva screen recognisable
 * before you read a word of it — a vessel filling, a surface that moves,
 * volume you can see rather than parse.
 *
 * Three rules hold across all of them, and they are what keep this an
 * operational tool rather than a demo reel:
 *
 *   1. DATA-DRIVEN. Every one takes real values. None of them invents a
 *      number, and none of them animates on a timer pretending to be data.
 *   2. THE NUMBER IS ALWAYS RENDERED. The liquid is reinforcement. Anyone who
 *      cannot see it, or has motion turned off, loses nothing.
 *   3. SURFACE MOVEMENT IS AMBIENT, NEVER URGENT. Amplitude is deliberately
 *      tiny — it reads as liquid peripherally and disappears under scrutiny.
 *      Anything that competes with the operator's task has failed.
 */

import { cn } from "@/lib/utils";

function pct(value: number, max: number): number {
  if (!(max > 0)) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}

/**
 * MilkFill — the primitive the others are built from: a vessel filling.
 *
 * The surface has a meniscus (a lighter band at the top) because that is what
 * makes it read as liquid rather than as a coloured rectangle.
 */
export function MilkFill({
  value,
  max = 100,
  label,
  tone = "dairy",
  still = false,
  className,
  children,
}: {
  value: number;
  max?: number;
  label: string;
  tone?: "dairy" | "fresh" | "water" | "amber";
  /** Paused/offline: the surface goes still. Stillness is a state, too. */
  still?: boolean;
  className?: string;
  children?: React.ReactNode;
}) {
  const filled = pct(value, max);
  const fill = {
    dairy: "bg-dairy",
    fresh: "bg-fresh",
    water: "bg-water",
    amber: "bg-amber",
  }[tone];
  const stroke = {
    dairy: "text-dairy",
    fresh: "text-fresh",
    water: "text-water",
    amber: "text-amber",
  }[tone];

  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(filled)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn("relative overflow-hidden rounded-xl bg-muted", className)}
    >
      <div
        className="absolute inset-x-0 bottom-0"
        style={{
          height: `${filled}%`,
          transition: "height var(--motion-flow) var(--ease-out-liquid)",
        }}
      >
        {/*
         * The curved surface. This is the difference between "liquid" and
         * "a coloured rectangle": real milk has a meniscus and never sits
         * perfectly flat, so the top of the fill is a drawn wave rather than
         * a straight edge.
         *
         * The wave is wider than the vessel and slides gently across it, so
         * the crest passing gives the impression of a surface settling
         * without anything visibly "animating". Amplitude is ~3px.
         */}
        <svg
          aria-hidden="true"
          viewBox="0 0 120 12"
          preserveAspectRatio="none"
          className={cn(
            "absolute -top-[9px] start-[-10%] h-3 w-[120%]",
            stroke,
            still ? "" : "lacteva-surface",
          )}
        >
          <path
            d="M0 8 Q 15 2, 30 8 T 60 8 T 90 8 T 120 8 L120 12 L0 12 Z"
            fill="currentColor"
          />
          {/* A lighter crest: light catches the top of a liquid surface. */}
          <path
            d="M0 8 Q 15 2, 30 8 T 60 8 T 90 8 T 120 8"
            fill="none"
            stroke="var(--milk)"
            strokeOpacity="0.45"
            strokeWidth="1.5"
          />
        </svg>

        <div className={cn("absolute inset-0", fill)} />
      </div>
      {children ? <div className="relative">{children}</div> : null}
    </div>
  );
}

/**
 * MilkVolume — a quantity, shown as volume.
 *
 * The number is the headline and the liquid is the context: "820 of 1,000 L"
 * is a fact, and seeing the vessel four-fifths full is an understanding.
 */
export function MilkVolume({
  value,
  max,
  unit = "L",
  label,
  caption,
  tone = "dairy",
  still = false,
  className,
}: {
  value: number;
  max: number;
  unit?: string;
  label: string;
  caption?: string;
  tone?: "dairy" | "fresh" | "water" | "amber";
  still?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <MilkFill
        value={value}
        max={max}
        label={label}
        tone={tone}
        still={still}
        className="h-24 w-14 shrink-0"
      />
      <div className="flex min-w-0 flex-col">
        <span className="text-meta uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span className="text-metric font-semibold tabular-nums tracking-tight">
          {value.toLocaleString()}
          <span className="ms-1 text-base font-normal text-muted-foreground">
            {unit}
          </span>
        </span>
        {caption ? (
          <span className="text-meta text-muted-foreground">{caption}</span>
        ) : null}
      </div>
    </div>
  );
}

/**
 * MilkStream — a horizontal flow, for a line or a route.
 *
 * Direction-aware: in a right-to-left page the stream travels the other way,
 * because a stream that flows against the reading direction reads as reverse.
 */
export function MilkStream({
  label,
  active = true,
  tone = "water",
  className,
}: {
  label: string;
  /** Idle streams do not move. Motion means something is happening. */
  active?: boolean;
  tone?: "water" | "fresh" | "dairy";
  className?: string;
}) {
  const line = { water: "bg-water/20", fresh: "bg-fresh/20", dairy: "bg-dairy/20" }[tone];
  const dot = { water: "bg-water", fresh: "bg-fresh", dairy: "bg-dairy" }[tone];
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div
        className={cn("relative h-1.5 flex-1 overflow-hidden rounded-full", line)}
        role="img"
        aria-label={label}
      >
        {active ? (
          <span
            aria-hidden="true"
            className="lacteva-flow absolute inset-0"
          />
        ) : null}
      </div>
      <span aria-hidden="true" className={cn("size-2 rounded-full", dot)} />
    </div>
  );
}

/**
 * MilkRipple — the completion beat.
 *
 * Fires once, on arrival, and then is gone. A success state that keeps
 * animating is a success state nobody believes.
 */
export function MilkRipple({
  children,
  className,
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex items-center justify-center", className)}>
      <span
        aria-hidden="true"
        className="lacteva-ripple absolute inset-0 rounded-full bg-success/40"
      />
      <span className="relative">{children}</span>
    </span>
  );
}

/**
 * CollectionProgress — a shift, as it fills.
 *
 * The one composite here, because "how is this centre doing today" is the
 * question the operational screens will ask most. It is a vessel, a number, a
 * target and a caption — no chart, because a chart of one value is decoration.
 */
export function CollectionProgress({
  collected,
  target,
  unit = "L",
  title,
  caption,
  paused = false,
  className,
}: {
  collected: number;
  target: number;
  unit?: string;
  title: string;
  caption?: string;
  /** Offline or shift-closed: the surface stills and the caption says why. */
  paused?: boolean;
  className?: string;
}) {
  const reached = pct(collected, target);
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-section font-semibold tracking-tight">{title}</span>
        <span className="text-meta tabular-nums text-muted-foreground">
          {Math.round(reached)}% of {target.toLocaleString()} {unit}
        </span>
      </div>
      <MilkFill
        value={collected}
        max={target}
        label={title}
        tone={reached >= 100 ? "fresh" : "dairy"}
        still={paused}
        className="h-3 w-full rounded-full"
      />
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-metric font-semibold tabular-nums tracking-tight">
          {collected.toLocaleString()}
          <span className="ms-1 text-base font-normal text-muted-foreground">{unit}</span>
        </span>
        {caption ? (
          <span className="text-meta text-muted-foreground">{caption}</span>
        ) : null}
      </div>
    </div>
  );
}
