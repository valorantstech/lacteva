"use client";

/**
 * A server-searchable picker for large directories (P1-PORTAL-SCALE-001).
 *
 * The audit's single highest-impact scale defect: supplier `<select>`s fed by
 * `listSuppliers({limit: 100})` — a dairy with 500 farmers could not record
 * milk for farmer #101 from the portal at all. This control asks the PLATFORM
 * instead: a debounced search hits the same tenant-scoped, permission-gated
 * list endpoint the pages already use, twenty rows at a time, with "load
 * more" for the tail. Nothing is prefetched, nothing is capped, and
 * authorization stays exactly where it was — on the backend.
 *
 * Deliberately built from the existing primitives (Input/Button, the list
 * pattern's borders) — no new visual language; the Design System milestone
 * comes later.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type PickerItem = {
  id: string;
  label: string;
  /** Secondary line — a code, a phone, a village. */
  detail?: string;
};

export type PickerPage = { items: PickerItem[]; total: number };

export function EntityPicker({
  id,
  label,
  placeholder,
  value,
  valueLabel,
  onSelect,
  search,
  allowClear = true,
  disabled = false,
  className,
}: {
  /** htmlFor identity of the search input. */
  id: string;
  label: string;
  placeholder?: string;
  /** The selected entity's id, or empty for none. */
  value: string;
  /** What to show for the selected id (the caller knows the name it picked). */
  valueLabel?: string;
  onSelect: (id: string, label: string) => void;
  /** Server-backed page of matches — the platform filters and counts. */
  search: (q: string, offset: number) => Promise<PickerPage>;
  allowClear?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<PickerItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const rootRef = useRef<HTMLDivElement>(null);

  const run = useCallback(
    async (query: string, offset: number) => {
      const mine = ++seq.current;
      setLoading(true);
      setError(null);
      try {
        const page = await search(query, offset);
        if (mine !== seq.current) return; // a newer keystroke owns the box
        setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
        setTotal(page.total);
      } catch {
        if (mine === seq.current) setError("Could not search — try again");
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    },
    [search],
  );

  // Debounced server search while open.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => void run(q, 0), 250);
    return () => clearTimeout(t);
  }, [open, q, run]);

  // Light dismissal: click outside or Escape closes the list.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const shown = items.length;

  return (
    <div className={className} ref={rootRef}>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        {value && !open ? (
          <div className="flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 text-sm">
            <span className="truncate">{valueLabel ?? `${value.slice(0, 8)}…`}</span>
            <span className="flex shrink-0 gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={() => {
                  setQ("");
                  setOpen(true);
                }}
              >
                Change
              </Button>
              {allowClear ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={disabled}
                  aria-label={`Clear ${label}`}
                  onClick={() => onSelect("", "")}
                >
                  ×
                </Button>
              ) : null}
            </span>
          </div>
        ) : (
          <Input
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-controls={`${id}-listbox`}
            autoComplete="off"
            placeholder={placeholder ?? "Type to search…"}
            disabled={disabled}
            value={q}
            onFocus={() => setOpen(true)}
            onChange={(e) => setQ(e.target.value)}
          />
        )}
      </div>

      {open ? (
        <div className="relative">
          <div
            id={`${id}-listbox`}
            role="listbox"
            aria-label={label}
            className="absolute z-20 mt-1 flex max-h-72 w-full min-w-64 flex-col overflow-y-auto rounded-md border border-border bg-background shadow-md"
          >
            {error ? (
              <div className="flex items-center justify-between gap-2 p-3 text-sm text-destructive">
                <span role="alert">{error}</span>
                <Button type="button" variant="outline" size="sm" onClick={() => void run(q, 0)}>
                  Retry
                </Button>
              </div>
            ) : null}
            {!error && loading && shown === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">Searching…</p>
            ) : null}
            {!error && !loading && shown === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                {q ? `Nothing matches “${q}”.` : "Nothing to choose from yet."}
              </p>
            ) : null}
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={item.id === value}
                className="flex flex-col items-start gap-0.5 border-b border-border/50 px-3 py-2 text-start text-sm last:border-b-0 hover:bg-muted focus-visible:bg-muted"
                onClick={() => {
                  onSelect(item.id, item.label);
                  setOpen(false);
                }}
              >
                <span className="font-medium">{item.label}</span>
                {item.detail ? (
                  <span className="text-xs text-muted-foreground">{item.detail}</span>
                ) : null}
              </button>
            ))}
            {shown > 0 && shown < total ? (
              <div className="flex items-center justify-between gap-2 border-t border-border p-2 text-xs text-muted-foreground">
                {/* The count is the platform's own total — never pretend the
                    visible slice is everything. */}
                <span aria-live="polite">
                  Showing {shown} of {total} — keep typing to narrow
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={loading}
                  onClick={() => void run(q, shown)}
                >
                  {loading ? "Loading…" : "Load more"}
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
