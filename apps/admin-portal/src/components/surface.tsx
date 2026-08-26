/**
 * Card hierarchy (Design System V1.1).
 *
 * The first pass gave every card the same flat outline, which is why the page
 * read as documentation: when everything is a bordered rectangle, nothing is
 * more important than anything else.
 *
 * Hierarchy here comes from ELEVATION and SURFACE, not from borders. A quiet
 * card sits on the page; a metric card lifts off it; a hero card is lit. The
 * page beneath is cream, so a milk-white card separates from it without a
 * line being drawn at all.
 *
 * Deliberately restrained: three elevations, one gradient angle, 2px of lift.
 * This is a platform someone uses for eight hours, not a landing page.
 */

import { cn } from "@/lib/utils";

type Tone = "quiet" | "metric" | "insight" | "operational" | "warning" | "live" | "hero";

const TONES: Record<Tone, string> = {
  // Sits on the page. For reference material and secondary panels.
  quiet: "bg-card border border-border",
  // Lifts off it. For the numbers someone came to the page to read.
  metric: "bg-card border border-border/60 shadow-[var(--elevation-2)]",
  // The intelligence surface — tinted, never filled.
  insight:
    "border border-intelligence/25 bg-[image:var(--gradient-intelligence)] shadow-[var(--elevation-1)]",
  // Work in progress: a live operational panel.
  operational:
    "bg-[image:var(--gradient-milk)] border border-border/60 shadow-[var(--elevation-2)]",
  // Attention, not alarm. Amber edge, quiet ground.
  warning: "border border-warning/40 bg-warning/5 shadow-[var(--elevation-1)]",
  // Something is happening right now.
  live: "border border-water/30 bg-water/5 shadow-[var(--elevation-1)]",
  // The top of a page. Lit, deep, and used once.
  hero:
    "bg-[image:var(--gradient-dairy)] text-primary-foreground border border-dairy-deep/40 shadow-[var(--elevation-3)]",
};

export function Surface({
  tone = "quiet",
  lift = false,
  className,
  children,
  ...props
}: {
  tone?: Tone;
  /** Interactive surfaces lift on hover. Static ones must not — a card that
   *  moves when you pass over it and does nothing when you click is a lie. */
  lift?: boolean;
  className?: string;
  children?: React.ReactNode;
} & React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-xl p-5",
        TONES[tone],
        lift && "lacteva-lift cursor-pointer",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

/**
 * A metric, at the size a metric deserves.
 *
 * The delta is text as well as colour and arrow — the house rule that colour
 * is never the only signal applies to trends too.
 */
export function Metric({
  label,
  value,
  unit,
  delta,
  caption,
  onBrand = false,
  className,
}: {
  label: string;
  /**
   * Pre-formatted, or a component that formats itself.
   *
   * Money and quantities arrive as `<Money>` / `<Quantity>`, which render the
   * platform's exact decimal string — this must never become a number here,
   * and `foundation.test.tsx` is what says so.
   */
  value: React.ReactNode;
  unit?: string;
  delta?: { direction: "up" | "down" | "flat"; text: string };
  /**
   * Metadata under the figure. ReactNode, not string, for the same reason
   * `value` is: a caption is often an exact money figure, and it must be
   * rendered by <Money> rather than interpolated into a template.
   */
  caption?: React.ReactNode;
  /**
   * Rendered on the brand ground (the hero) rather than on milk.
   *
   * This is not a styling convenience — it is a correctness switch. The
   * default supporting colours (`--muted-foreground`, `--success`,
   * `--destructive`) are tuned for a milk ground and effectively DISAPPEAR on
   * deep green: the hero's labels, units, deltas and captions were all
   * failing contrast. The on-brand tokens are their measured counterparts,
   * and they flip correctly between the light and dark faces.
   */
  onBrand?: boolean;
  className?: string;
}) {
  const supporting = onBrand ? "text-on-brand-muted" : "text-muted-foreground";
  const tone = onBrand
    ? delta?.direction === "up"
      ? "text-on-brand-positive"
      : delta?.direction === "down"
        ? "text-on-brand-negative"
        : "text-on-brand-muted"
    : delta?.direction === "up"
      ? "text-success"
      : delta?.direction === "down"
        ? "text-destructive"
        : "text-muted-foreground";
  const arrow =
    delta?.direction === "up" ? "▲" : delta?.direction === "down" ? "▼" : "—";

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className={cn("text-meta uppercase tracking-wide", supporting)}>
        {label}
      </span>
      <span
        className={cn(
          "text-metric font-semibold tabular-nums tracking-tight",
          onBrand && "text-on-brand",
        )}
      >
        {value}
        {unit ? (
          <span className={cn("ms-1 text-base font-normal", supporting)}>{unit}</span>
        ) : null}
      </span>
      {delta ? (
        <span className={cn("text-meta font-medium", tone)}>
          <span aria-hidden="true">{arrow} </span>
          {delta.text}
        </span>
      ) : null}
      {caption ? (
        <span className={cn("text-meta", supporting)}>{caption}</span>
      ) : null}
    </div>
  );
}
