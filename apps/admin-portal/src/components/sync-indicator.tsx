/**
 * Offline → syncing → synced, said plainly (Design System V1).
 *
 * The one status an operator must never have to guess. The readiness audit's
 * six operator questions include "did it save?" and "is it queued?", and this
 * is the portal half of that answer.
 *
 * Three rules, all of them accessibility rules as much as design rules:
 *   1. The WORD is always rendered. Colour and motion are reinforcement, never
 *      the signal — the same rule `foundation.test.tsx` already enforces for
 *      status badges.
 *   2. The count is always rendered when work is waiting. "3 waiting" is
 *      actionable; a coloured dot is not.
 *   3. Changes are announced politely, so a screen-reader user learns that a
 *      queue drained without having to go looking.
 *
 * Only `syncing` animates, and it animates because something really is in
 * progress. A resting state that pulses is noise.
 */
import { cn } from "@/lib/utils";

export type SyncState = "online" | "offline" | "syncing" | "error";

export function SyncIndicator({
  state,
  pending = 0,
  labels,
  className,
}: {
  state: SyncState;
  /** How many captures are waiting. Rendered whenever it is above zero. */
  pending?: number;
  /** Caller-supplied so this is translatable; English is only the fallback. */
  labels?: Partial<Record<SyncState, string>> & { pending?: string };
  className?: string;
}) {
  const text: Record<SyncState, string> = {
    online: labels?.online ?? "Online",
    offline: labels?.offline ?? "Offline — work is saved on this device",
    syncing: labels?.syncing ?? "Syncing…",
    error: labels?.error ?? "Sync failed",
  };

  const tone: Record<SyncState, string> = {
    online: "text-success border-success/30 bg-success/5",
    offline: "text-warning border-warning/30 bg-warning/5",
    syncing: "text-water border-water/30 bg-water/5",
    error: "text-destructive border-destructive/30 bg-destructive/5",
  };

  return (
    <div
      // Polite, not assertive: a sync finishing must not interrupt whatever
      // the person is reading.
      role="status"
      aria-live="polite"
      className={cn(
        "relative inline-flex items-center gap-2 overflow-hidden rounded-full border px-3 py-1 text-sm",
        tone[state],
        className,
      )}
    >
      {/* The flow band, only while something is actually moving. */}
      {state === "syncing" ? (
        <>
          <span aria-hidden="true" className="lacteva-flow pointer-events-none absolute inset-0" />
          {/*
           * Droplets travelling toward the destination. The metaphor is the
           * thing an operator actually wants to know: work is LEAVING this
           * device and ARRIVING somewhere. Three, staggered, low contrast —
           * enough to read as movement, not enough to distract.
           */}
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              aria-hidden="true"
              className="lacteva-droplet pointer-events-none absolute top-1/2 size-1 rounded-full bg-water/70"
              style={{
                insetInlineStart: "0.5rem",
                ["--droplet-distance" as string]: "2.5rem",
                animationDelay: `${i * 600}ms`,
              }}
            />
          ))}
        </>
      ) : null}

      {/* A shape as well as a colour, for anyone who cannot separate the two. */}
      <span aria-hidden="true" className="relative text-xs leading-none">
        {state === "online" ? "●" : state === "offline" ? "◐" : state === "syncing" ? "◍" : "▲"}
      </span>

      <span className="relative font-medium">{text[state]}</span>

      {pending > 0 ? (
        <span className="relative tabular-nums opacity-80">
          · {pending} {labels?.pending ?? "waiting"}
        </span>
      ) : null}
    </div>
  );
}
