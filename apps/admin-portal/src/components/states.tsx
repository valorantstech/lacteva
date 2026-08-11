/**
 * The four states every data view has, in one place (DEMO-001).
 *
 * Loading, empty, error and "you cannot see this" are not edge cases — they
 * are most of what an operator experiences on a slow morning, and a screen
 * that renders each of them differently teaches nobody anything. The dashboard
 * crash in PILOT-001 was exactly this: a page that believed a response body
 * before checking whether the request had succeeded.
 *
 * An empty state says WHY it is empty and what to do next. "No data" is a
 * dead end; "No collections today — open a session at a centre to begin" is
 * an instruction.
 */

import type { ReactNode } from "react";
import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"
    >
      <Loader2 aria-hidden className="size-4 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

/**
 * Skeleton rows. Used where the SHAPE of what is coming is already known —
 * it stops the page jumping when the data lands.
 */
export function TableSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div aria-hidden className="flex flex-col gap-2 py-2">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: columns }).map((_, c) => (
            <div
              key={c}
              className="h-4 flex-1 animate-pulse rounded bg-muted"
              style={{ animationDelay: `${(r * columns + c) * 40}ms` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border px-6 py-12 text-center">
      <div className="text-muted-foreground" aria-hidden>
        {icon ?? <Inbox className="size-6" />}
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description ? (
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/**
 * An error the user can act on. `role="alert"` because a failure that only
 * appears visually is invisible to anyone using a screen reader, and the icon
 * is decorative — the words carry the meaning, never the colour alone.
 */
export function ErrorState({
  message,
  action,
  className,
}: {
  message: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3",
        className,
      )}
    >
      <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div className="flex flex-col gap-2">
        <p className="text-sm text-destructive">{message}</p>
        {action}
      </div>
    </div>
  );
}
