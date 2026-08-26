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
import { useT } from "@/lib/i18n";
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
      ) : rows.length > 0 ? (
        // Wide business tables scroll horizontally rather than being crushed:
        // a settlement line with eight figures is not improved by wrapping.
        <div className="w-full overflow-x-auto">
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
        </div>
      ) : null}

      {page ? <Pagination {...page} /> : null}
    </div>
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
