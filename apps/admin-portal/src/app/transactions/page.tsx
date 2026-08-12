"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Activity, Banknote, Droplets, Percent, Plus } from "lucide-react";
import {
  ApiError,
  type Center,
  type DailyCollectionSummary,
  type MilkTransaction,
  type MilkTransactionPage,
  type OperationalStatus,
  type Supplier,
  getDailyReport,
  getOperationalStatus,
  listCenters,
  listMilkTransactions,
  listSuppliers,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { type DateRange, DateRangePicker, resolveRange } from "@/components/date-range";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

/**
 * Transactions — the operational view (DEMO-004, rebuilt in DEMO-007).
 *
 * This is the screen an operations manager lives in, so it answers the
 * question they actually ask: not "what was collected" but "where has each
 * collection got to". That means the financial columns — settled, paid — sit
 * on the same row as the milk.
 *
 * Two rules make that affordable and honest:
 *
 * 1. EVERY FILTER IS A QUERY PARAMETER. State, centre, supplier and the date
 *    window are applied by the database over the whole table. The KPI row is
 *    the reporting module's `daily` aggregate over the same window, so the
 *    numbers above the table and the rows inside it answer the same question,
 *    computed once, in one place.
 *
 * 2. THE FINANCIAL COLUMNS COST ONE CALL, NOT ONE PER ROW. `/chain` answers
 *    "was this settled and paid?" for a single collection; asking it per row
 *    would be a fifty-request table. `getOperationalStatus()` asks it for the
 *    whole page at once, and the platform answers in a fixed number of
 *    queries. The status is fetched AFTER the page renders, so a slow
 *    financial join never delays the milk.
 *
 * Nothing here multiplies a quantity by a rate. The amount on each row is the
 * amount the pricing engine wrote.
 */

const PAGE_SIZE = 15;

/** The real lifecycle, in order. No invented states. */
const STATES = [
  "",
  "NEW",
  "SUPPLIER_IDENTIFIED",
  "MILK_RECEIVED",
  "WEIGHT_CAPTURED",
  "QUALITY_PENDING",
  "QUALITY_CAPTURED",
  "PRICING_PENDING",
  "PRICED",
  "ACCEPTED",
  "REJECTED",
  "COMPLETED",
  "CANCELLED",
] as const;

/**
 * Settlement and payment status are shown as COLUMNS but not offered as
 * FILTERS, and that is deliberate.
 *
 * Those two facts live in other modules, so the collection list cannot filter
 * on them; the only way to offer the control would be to filter the fifteen
 * rows already in the browser. A "Settlement: finalized" control that quietly
 * means "…among the rows you happen to be looking at" is precisely the
 * dishonesty the server-side filters above exist to avoid, and it would be
 * worse here than nowhere, because the pagination total beneath it would still
 * read 360. Filtering by settlement status belongs on the settlements screen,
 * which can do it properly.
 *
 * The columns themselves never invent a status and never show a settled or
 * paid badge merely because a row exists — an absence is rendered as an
 * absence.
 */

const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Could not load collections";
};

/** `WeightCaptured` → `Weight captured` — sentence case, not Title Case. */
const humanise = (event: string) =>
  event
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_.]/g, " ")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "—";

export default function TransactionsPage() {
  const [page, setPage] = useState<MilkTransactionPage | null>(null);
  const [summary, setSummary] = useState<DailyCollectionSummary | null>(null);
  const [status, setStatus] = useState<Record<string, OperationalStatus>>({});
  const [centers, setCenters] = useState<Center[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const [range, setRange] = useState<DateRange>(() => resolveRange("30d"));
  const [state, setState] = useState<(typeof STATES)[number]>("");
  const [centerId, setCenterId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filtered = Boolean(state || centerId || supplierId);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = {
      state: state || undefined,
      center_id: centerId || undefined,
      supplier_id: supplierId || undefined,
      date_from: range.from,
      date_to: range.to,
      limit: PAGE_SIZE,
      offset,
    };
    try {
      const result = await listMilkTransactions(params);
      setPage(result);

      // ONE call for the whole page's financial position. Deliberately not
      // awaited with the page: the table is useful before the money arrives.
      const ids = (result.items ?? []).map((t) => t.id);
      getOperationalStatus(ids)
        .then((r) =>
          setStatus(Object.fromEntries((r.items ?? []).map((s) => [s.transaction_id, s]))),
        )
        .catch(() => setStatus({}));

      // The KPI row is a separate aggregate over the same window; a reporting
      // hiccup must not blank the table.
      getDailyReport({
        date_from: range.from,
        date_to: range.to,
        center_id: centerId || undefined,
        supplier_id: supplierId || undefined,
      })
        .then(setSummary)
        .catch(() => setSummary(null));
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [centerId, offset, range.from, range.to, state, supplierId]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    listCenters({ limit: 100, offset: 0 })
      .then((c) => setCenters(c.items ?? []))
      .catch(() => setCenters([]));
    listSuppliers({ limit: 100, offset: 0 })
      .then((s) => setSuppliers(s.items ?? []))
      .catch(() => setSuppliers([]));
  }, []);

  const names = useMemo(
    () => ({
      centers: Object.fromEntries(centers.map((c) => [c.id, c.name])),
      suppliers: Object.fromEntries(suppliers.map((s) => [s.id, s.full_name])),
    }),
    [centers, suppliers],
  );

  const currencies = Object.entries(summary?.payable_by_currency ?? {});
  const primary = currencies[0];

  const columns: Column<MilkTransaction>[] = [
    {
      key: "when",
      header: "Collected",
      cell: (tx) => (
        <div className="flex flex-col">
          <Link className="font-medium hover:underline" href={`/transactions/${tx.id}`}>
            {String(tx.created_at).slice(0, 10)}
          </Link>
          <span className="text-xs text-muted-foreground">
            {String(tx.created_at).slice(11, 16)} · {tx.id.slice(0, 8)}
          </span>
        </div>
      ),
    },
    {
      key: "supplier",
      header: "Supplier",
      cell: (tx) =>
        tx.supplier_id ? (
          <Link className="hover:underline" href={`/suppliers/${tx.supplier_id}`}>
            {names.suppliers[tx.supplier_id] ?? `${tx.supplier_id.slice(0, 8)}…`}
          </Link>
        ) : (
          <span className="text-muted-foreground">not identified</span>
        ),
    },
    {
      key: "center",
      header: "Centre",
      secondary: true,
      cell: (tx) => (
        <Link className="hover:underline" href={`/centers/${tx.center_id}`}>
          {names.centers[tx.center_id] ?? `${tx.center_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    {
      key: "quantity",
      header: "Quantity",
      align: "end",
      cell: (tx) => <Quantity value={tx.net_weight} unit={tx.weight_unit ?? "kg"} />,
    },
    {
      key: "quality",
      header: "Quality",
      align: "end",
      secondary: true,
      cell: (tx) =>
        tx.fat != null || tx.snf != null ? (
          <span className="tabular-nums text-sm">
            {tx.fat != null ? `${tx.fat}% fat` : "—"}
            {tx.snf != null ? ` · ${tx.snf}% snf` : ""}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "rate",
      header: "Rate",
      align: "end",
      secondary: true,
      cell: (tx) =>
        tx.unit_price != null ? (
          <span className="tabular-nums">{String(tx.unit_price)}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "value",
      header: "Value",
      align: "end",
      cell: (tx) => <Money amount={tx.gross_amount} currency={tx.currency} />,
    },
    { key: "state", header: "Status", cell: (tx) => <StatusBadge status={tx.state} /> },
    {
      key: "settlement",
      header: "Settlement",
      cell: (tx) => {
        const s = status[tx.id];
        if (!s?.settlement_id)
          return <span className="text-xs text-muted-foreground">not settled</span>;
        return (
          <div className="flex flex-col items-start gap-0.5">
            <Link className="text-sm hover:underline" href={`/settlements/${s.settlement_id}`}>
              {s.settlement_number}
            </Link>
            <StatusBadge status={s.settlement_status} />
          </div>
        );
      },
    },
    {
      key: "payment",
      header: "Payment",
      cell: (tx) => {
        const s = status[tx.id];
        if (!s?.payment_id)
          return <span className="text-xs text-muted-foreground">not paid</span>;
        return (
          <div className="flex flex-col items-start gap-0.5">
            <Link className="text-sm hover:underline" href={`/payments/${s.payment_id}`}>
              {s.payment_number}
            </Link>
            <StatusBadge status={s.payment_status} />
          </div>
        );
      },
    },
    {
      key: "activity",
      header: "Last activity",
      secondary: true,
      cell: (tx) => {
        const s = status[tx.id];
        if (!s?.last_event_type) return <span className="text-muted-foreground">—</span>;
        return (
          <div className="flex flex-col">
            <span className="text-sm">{humanise(s.last_event_type)}</span>
            <span className="text-xs text-muted-foreground">{stamp(s.last_event_at)}</span>
          </div>
        );
      },
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (tx) => (
        <Link
          href={`/transactions/${tx.id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          Open
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[100rem] flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Transactions"
        description="Every delivery of milk, priced by the rate card in force at the moment it was received — and where its money has got to."
        actions={
          <Link
            href="/transactions/new"
            className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            <Plus aria-hidden className="mr-1.5 size-4" />
            Record collection
          </Link>
        }
      />

      <DateRangePicker value={range} onChange={setRange} busy={loading} />

      <section aria-label="Collection summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Collections"
          value={summary ? summary.transactions : "—"}
          hint={
            summary ? `${summary.accepted} accepted · ${summary.rejected} rejected` : undefined
          }
          icon={<Activity className="size-4" />}
        />
        <StatTile
          label="Quantity"
          value={summary ? <Quantity value={summary.total_net_weight_kg} unit="kg" /> : "—"}
          hint={summary ? `${summary.suppliers_served} suppliers` : undefined}
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label="Value"
          value={
            primary ? (
              <Money amount={primary[1]} currency={primary[0]} />
            ) : summary ? (
              <Money amount="0.00" currency="KES" />
            ) : (
              "—"
            )
          }
          icon={<Banknote className="size-4" />}
        />
        <StatTile
          label="Average fat"
          value={summary?.weighted_avg_fat != null ? `${summary.weighted_avg_fat}%` : "—"}
          hint="weighted by quantity"
          icon={<Percent className="size-4" />}
        />
      </section>

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Milk collections in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(tx) => tx.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered
                ? "No collection matches these filters"
                : "No collections in this period",
              description: filtered
                ? "Try a wider date range, or clear the filters."
                : "Open a session at a centre and record a delivery to begin.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tx-state">Status</Label>
                  <select
                    id="tx-state"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={state}
                    onChange={(e) => {
                      setState(e.target.value as (typeof STATES)[number]);
                      setOffset(0);
                    }}
                  >
                    {STATES.map((s) => (
                      <option key={s || "all"} value={s}>
                        {s ? s.toLowerCase().replace(/_/g, " ") : "All statuses"}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tx-center">Centre</Label>
                  <select
                    id="tx-center"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={centerId}
                    onChange={(e) => {
                      setCenterId(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All centres</option>
                    {centers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tx-supplier">Supplier</Label>
                  <select
                    id="tx-supplier"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={supplierId}
                    onChange={(e) => {
                      setSupplierId(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All suppliers</option>
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.full_name}
                      </option>
                    ))}
                  </select>
                </div>
                {filtered ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setState("");
                      setCenterId("");
                      setSupplierId("");
                      setOffset(0);
                    }}
                  >
                    Clear filters
                  </Button>
                ) : null}
              </>
            }
            page={{
              offset,
              limit: PAGE_SIZE,
              total: page?.total ?? 0,
              onChange: setOffset,
              busy: loading,
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}
