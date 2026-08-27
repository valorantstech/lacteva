"use client";

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
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function LoadingState({ label }: { label?: string }) {
  // P1-PORTAL-SCALE-001: the shared chrome speaks the catalog's language —
  // a Hindi operator was getting a Hindi sidebar over English scaffolding.
  const t = useT();
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"
    >
      <Loader2 aria-hidden className="size-4 animate-spin" />
      <span>{label ?? t("state.loading")}</span>
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
              className="lacteva-skeleton h-4 flex-1 rounded"
              style={{ animationDelay: `${(r * columns + c) * 40}ms` }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * A list that is not the whole list, saying so (LACTEVA-ADMIN-007).
 *
 * Several screens fetch a fixed first page — a hundred centres, fifty
 * payments, ten receipts — and then render exactly what came back. For most
 * dairies that is everything, so the cap is invisible; for the one dairy it is
 * not, the list simply ends, and nothing on the screen says the rest exists.
 * A centre that cannot be selected looks like a centre that was never created.
 *
 * The platform returns an authoritative `total` on every one of those calls,
 * so the honest thing was always available and merely unread. Nothing here
 * counts anything: `total` is the platform's number, `shown` is what the page
 * actually rendered, and the notice appears only when they disagree.
 */
export function CappedNotice({
  shown,
  total,
  noun,
  hint,
}: {
  shown: number;
  total: number;
  /** Plural, lower case — "centres", "payments", "receipts". */
  noun: string;
  /** What to do about the ones that are not here. */
  hint?: string;
}) {
  if (total <= shown) return null;
  return (
    <p className="text-meta text-muted-foreground" role="status" aria-live="polite">
      {`Showing ${shown} of ${total} ${noun}.`}
      {hint ? ` ${hint}` : ""}
    </p>
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
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-border/60 bg-muted/30 px-6 py-14 text-center">
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
