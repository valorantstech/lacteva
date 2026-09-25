"use client";

/**
 * One table pattern for every list in the portal (DEMO-001).
 *
 * Eight screens list rows and every one of them needs the same four states,
 * the same toolbar and the same pagination. Writing that eight times is eight
 * chances for "no results" to mean something different, and eight places to
 * fix when it is wrong.
 *
 * Deliberately NOT a grid framework. No client-side sorting, filtering or
 * paging: the platform pages and filters server-side, the row counts are
 * authoritative, and a table that quietly sorts only the page it can see lies
 * about the data. Columns are plain render functions, so a cell can use
 * `<Money>` or `<StatusBadge>` without this component knowing what money is.
 */

import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { ScrollHint } from "@/components/scroll-hint";
import { useT } from "@/lib/i18n";
import { useIsNarrow } from "@/lib/viewport";
import { cn } from "@/lib/utils";

export type Column<T> = {
  /** Stable key — also the header's `scope="col"` identity. */
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Right-align money and quantities so digits line up down the column. */
  align?: "start" | "end";
  /** Hidden below `md`, for columns that are context rather than content. */
  secondary?: boolean;
  /**
   * WO-96: what the column IS, so the phone can lay a row out as a card —
   * the identity as the heading, the money right beside it and large, the
   * status as a chip, the actions as full-width buttons at the bottom, and
   * everything else as a label/value line. The desktop table ignores it.
   * Unset means "meta".
   */
  role?: "title" | "subtitle" | "money" | "status" | "actions" | "meta";
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  error = null,
  empty,
  toolbar,
  caption,
  onRetry,
  page,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: string | null;
  empty?: { title: string; description?: string; action?: ReactNode };
  toolbar?: ReactNode;
  /** Screen-reader description of what the table holds. */
  caption: string;
  onRetry?: () => void;
  page?: PaginationProps;
}) {
  const showSkeleton = loading && rows.length === 0;
  const narrow = useIsNarrow();
  // Shared chrome goes through the catalog (P1-PORTAL-SCALE-001): these
  // strings frame every list in the portal, so they must not stay English
  // when the session is not.
  const t = useT();

  return (
    <div className="flex flex-col gap-4">
      {toolbar ? <div className="flex flex-wrap items-end gap-3">{toolbar}</div> : null}

      {error ? (
        <ErrorState
          message={error}
          action={
            onRetry ? (
              <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                {t("error.tryAgain")}
              </Button>
            ) : null
          }
        />
      ) : null}

      {showSkeleton ? (
        <TableSkeleton rows={5} columns={columns.length} />
      ) : rows.length === 0 && !error ? (
        <EmptyState
          title={empty?.title ?? t("table.nothingHere")}
          description={empty?.description}
          action={empty?.action}
        />
      ) : rows.length > 0 && narrow ? (
        <RowCards columns={columns} rows={rows} rowKey={rowKey} caption={caption} loading={loading} />
      ) : rows.length > 0 ? (
        // Wide business tables scroll horizontally rather than being crushed:
        // a settlement line with eight figures is not improved by wrapping —
        // and the scroller says it scrolls (WO-96 §3).
        <ScrollHint>
          <Table>
            <caption className="sr-only">{caption}</caption>
            <TableHeader>
              <TableRow>
                {columns.map((c) => (
                  <TableHead
                    key={c.key}
                    scope="col"
                    className={cn(
                      // Design System V1: a header is a LABEL, not another row
                      // of data. Smaller, uppercase and quiet, so the eye goes
                      // to the figures rather than to the column names.
                      "text-meta font-semibold uppercase tracking-wide text-muted-foreground",
                      c.align === "end" && "text-end",
                      c.secondary && "hidden md:table-cell",
                    )}
                  >
                    {c.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody className={cn(loading && "opacity-60 transition-opacity")}>
              {rows.map((row) => (
                <TableRow
                  key={rowKey(row)}
                  // Reading a wide row is the commonest thing anyone does in
                  // this product; the tint follows the eye across it.
                  className="transition-colors duration-[var(--motion-instant)] hover:bg-muted/40"
                >
                  {columns.map((c) => (
                    <TableCell
                      key={c.key}
                      className={cn(
                        c.align === "end" && "text-end",
                        c.secondary && "hidden md:table-cell",
                      )}
                    >
                      {c.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollHint>
      ) : null}

      {page ? <Pagination {...page} /> : null}
    </div>
  );
}

/**
 * The same rows as cards, for a phone (WO-96 §1). Driven by the SAME column
 * definitions as the table, so a column added later appears in both — the
 * one thing a hand-built mobile layout per page could never promise. The
 * header of a `meta` column becomes its label; `secondary` columns are
 * shown here too, because on a card there is room for context.
 */
function RowCards<T>({
  columns,
  rows,
  rowKey,
  caption,
  loading,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption: string;
  loading: boolean;
}) {
  const by = (role: NonNullable<Column<T>["role"]>) => columns.filter((c) => (c.role ?? "meta") === role);
  const title = by("title");
  const subtitle = by("subtitle");
  const money = by("money");
  const status = by("status");
  const actions = by("actions");
  const meta = by("meta");
  return (
    <ul
      aria-label={caption}
      data-testid="row-cards"
      className={cn("flex flex-col gap-3", loading && "opacity-60 transition-opacity")}
    >
      {rows.map((row) => (
        <li
          key={rowKey(row)}
          data-testid="row-card"
          className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3 text-sm shadow-xs"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {title.map((c) => (
                <div key={c.key} className="font-medium leading-snug" data-role="title">
                  {c.cell(row)}
                </div>
              ))}
              {subtitle.map((c) => (
                <div key={c.key} className="text-xs text-muted-foreground" data-role="subtitle">
                  {c.cell(row)}
                </div>
              ))}
            </div>
            {money.length > 0 ? (
              <div className="flex shrink-0 flex-col items-end gap-0.5" data-role="money">
                {money.map((c) => (
                  <div key={c.key} className="text-end">
                    {money.length > 1 ? (
                      <span className="me-1 text-xs text-muted-foreground">{c.header}</span>
                    ) : null}
                    <span className="text-lg font-semibold tabular-nums">{c.cell(row)}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          {status.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2" data-role="status">
              {status.map((c) => (
                <span key={c.key}>{c.cell(row)}</span>
              ))}
            </div>
          ) : null}
          {meta.length > 0 ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs" data-role="meta">
              {meta.map((c) => (
                <div key={c.key} className="contents">
                  <dt className="text-muted-foreground">{c.header}</dt>
                  <dd className="min-w-0 text-end">{c.cell(row)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {actions.length > 0 ? (
            <div
              className="flex flex-col gap-2 border-t border-border pt-2 [&_a]:w-full [&_a]:justify-center [&_button]:w-full [&_button]:justify-center"
              data-role="actions"
            >
              {actions.map((c) => (
                <div key={c.key} className="flex flex-col gap-2">
                  {c.cell(row)}
                </div>
              ))}
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export type PaginationProps = {
  /** Zero-based offset, as the platform's own list endpoints use. */
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
  busy?: boolean;
};

export function Pagination({ offset, limit, total, onChange, busy }: PaginationProps) {
  // Hook before the early return — the rules of hooks do not pause for
  // empty tables.
  const t = useT();
  if (total === 0) return null;
  const first = offset + 1;
  const last = Math.min(offset + limit, total);
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-meta text-muted-foreground" aria-live="polite">
        {t("table.showing", { from: first, to: last, total })}
      </p>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canPrev || busy}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          {t("table.previous")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canNext || busy}
          onClick={() => onChange(offset + limit)}
        >
          {t("table.next")}
        </Button>
      </div>
    </div>
  );
}
