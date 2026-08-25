"use client";

/**
 * The intelligence treatment (Design System V1.1).
 *
 * Lacteva computes exactly one such thing today: a statistical deviation flag
 * on collection quality. Every other item in this family is an unbuilt roadmap
 * entry (they are enumerated, and labelled, on the roadmap page — naming them
 * anywhere else is precisely what the claims guards refuse).
 *
 * V1.1 makes the treatment visually distinct without making it magical, which
 * is a narrow path. The rules that keep it on that path:
 *
 *   EVIDENCE FIRST. The basis is not a footnote under the headline — it is
 *   the second line, in the reading order, always rendered. `basis` is a
 *   required prop and there is no variant without it. An insight whose reason
 *   is hidden behind a chevron is an oracle with extra steps.
 *
 *   CONFIDENCE IS SHOWN AS A RANGE, NOT A SCORE. "High" with a filled bar
 *   invites trust that statistics has not earned. The label is a word, the
 *   bar is unfilled space as much as filled, and it is optional — a signal
 *   that cannot honestly carry confidence simply does not pass it.
 *
 *   GLOW, NEVER FILL. Indigo tint and a soft outer glow. A large solid indigo
 *   panel would out-shout the operator's actual work, and an interface that
 *   shouts whenever software had an opinion trains people to ignore it.
 *
 *   IT CANNOT SAY IT IS AVAILABLE. There is no prop for that. A roadmap
 *   capability gets `ComingSoonInsight`, which says so in words.
 */

import { useState } from "react";

import { cn } from "@/lib/utils";

export type Confidence = "low" | "moderate" | "high";

const CONFIDENCE_FILL: Record<Confidence, string> = {
  low: "w-1/3",
  moderate: "w-2/3",
  high: "w-full",
};

export function Insight({
  title,
  basis,
  confidence,
  confidenceLabel,
  reasoning,
  reasoningLabel = "How this was determined",
  className,
}: {
  /** What was noticed. */
  title: string;
  /** WHY — the rule or comparison behind it. Required, and always visible. */
  basis: string;
  /** Optional: omit it rather than guess. */
  confidence?: Confidence;
  confidenceLabel?: string;
  /** The long form, for someone who wants to audit the signal. */
  reasoning?: string;
  reasoningLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-intelligence/25 p-4",
        "bg-[image:var(--gradient-intelligence)]",
        className,
      )}
      style={{ boxShadow: "var(--glow-intelligence)" }}
    >
      <div className="flex items-start gap-3">
        {/* A slow breath, never a blink: a blinking badge reads as an alarm. */}
        <span
          aria-hidden="true"
          className="lacteva-attend mt-0.5 text-lg leading-none text-intelligence"
        >
          ◆
        </span>

        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-meta font-semibold uppercase tracking-wider text-intelligence">
              Signal
            </span>
            {confidence ? (
              <span className="flex items-center gap-1.5">
                <span className="text-meta text-muted-foreground">
                  {confidenceLabel ?? `${confidence} confidence`}
                </span>
                {/* Deliberately a partial bar. Unfilled space is information. */}
                <span
                  aria-hidden="true"
                  className="h-1 w-10 overflow-hidden rounded-full bg-intelligence/15"
                >
                  <span
                    className={cn("block h-full rounded-full bg-intelligence/70", CONFIDENCE_FILL[confidence])}
                  />
                </span>
              </span>
            ) : null}
          </div>

          <span className="text-sm font-medium text-foreground">{title}</span>

          {/* Evidence, in the reading order, always. */}
          <span className="text-meta text-muted-foreground">{basis}</span>

          {reasoning ? (
            <div className="mt-1">
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                className="text-meta font-medium text-intelligence underline-offset-4 hover:underline"
              >
                {reasoningLabel}
                <span aria-hidden="true">{open ? " ▴" : " ▾"}</span>
              </button>
              {open ? (
                <p className="lacteva-settle mt-2 rounded-lg bg-intelligence/5 p-3 text-meta text-muted-foreground">
                  {reasoning}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/**
 * The same family, saying plainly that it is not here yet.
 *
 * This exists so that someone reaching for the intelligence look on a roadmap
 * feature finds a component that tells the truth instead of one that lies.
 */
export function ComingSoonInsight({
  title,
  note,
  comingSoonLabel = "Coming soon",
  className,
}: {
  title: string;
  note?: string;
  comingSoonLabel?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 rounded-xl border border-dashed border-intelligence/30 p-4",
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        <span className="text-sm text-muted-foreground">{title}</span>
        {note ? <span className="text-meta text-muted-foreground/80">{note}</span> : null}
      </div>
      <span className="shrink-0 rounded-full border border-intelligence/40 px-2 py-0.5 text-meta font-medium text-intelligence">
        {comingSoonLabel}
      </span>
    </div>
  );
}
