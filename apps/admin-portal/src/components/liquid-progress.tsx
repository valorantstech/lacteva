/**
 * Progress as a vessel filling (Design System V1).
 *
 * The Lacteva progress shape: a bar fills from the bottom like milk in a
 * measure, rather than sliding left-to-right like every other dashboard. It
 * is the most recognisable piece of the visual language and it costs nothing
 * in clarity — the number is always rendered beside it.
 *
 * RTL-safe by construction: the fill is vertical, so it does not have a
 * direction to get wrong.
 *
 * Accessibility: a real `progressbar` with its value, and the percentage in
 * text. Colour is never the only signal.
 */
import { cn } from "@/lib/utils";

export function LiquidProgress({
  value,
  max = 100,
  label,
  className,
  tone = "dairy",
}: {
  value: number;
  max?: number;
  /** What is progressing. Required: an unlabelled progress bar is a mystery. */
  label: string;
  className?: string;
  tone?: "dairy" | "fresh" | "water";
}) {
  const safeMax = max > 0 ? max : 100;
  const pct = Math.max(0, Math.min(100, (value / safeMax) * 100));
  const fill =
    tone === "fresh" ? "bg-fresh" : tone === "water" ? "bg-water" : "bg-dairy";

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="relative h-10 w-3 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn("absolute inset-x-0 bottom-0 origin-bottom", fill)}
          style={{
            height: `${pct}%`,
            transition: "height var(--motion-slow) var(--ease-out-liquid)",
          }}
        />
      </div>
      <span className="text-sm tabular-nums text-muted-foreground">
        {Math.round(pct)}%
      </span>
    </div>
  );
}
