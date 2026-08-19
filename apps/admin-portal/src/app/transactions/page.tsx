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
  getDailyReport,
  getOperationalStatus,
  listCenters,
  listMilkTransactions,
  listSuppliers,
} from "@/lib/api";
import { EntityPicker } from "@/components/entity-picker";
import { useSupplierNames } from "@/lib/names";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { DateRangePicker, useDefaultRange } from "@/components/date-range";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useLocale } from "@/lib/i18n";

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

const describe = (e: unknown, fallback: string) => {
  if (e instanceof ApiError)
    return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : fallback;
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
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const { currency: orgCurrency, t } = useLocale();
  const [page, setPage] = useState<MilkTransactionPage | null>(null);
  const [summary, setSummary] = useState<DailyCollectionSummary | null>(null);
  const [status, setStatus] = useState<Record<string, OperationalStatus>>({});
  const [centers, setCenters] = useState<Center[]>([]);
  // P1-PORTAL-SCALE-001: the supplier filter searches the platform instead of
  // prefetching a capped list; the label remembers what was picked.
  const [supplierFilterLabel, setSupplierFilterLabel] = useState("");

  // Derived until the reader chooses, so a timezone that arrives after the
  // first render still corrects the window (DEMO-019).
  const [range, setRange] = useDefaultRange("30d");
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
          setStatus(
            Object.fromEntries(
              (r.items ?? []).map((s) => [s.transaction_id, s]),
            ),
          ),
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
      setError(describe(err, t("tx.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [centerId, offset, range.from, range.to, state, supplierId, t]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    listCenters({ limit: 100, offset: 0 })
      .then((c) => setCenters(c.items ?? []))
      .catch(() => setCenters([]));
  }, []);

  const names = useMemo(
    () => ({
      centers: Object.fromEntries(centers.map((c) => [c.id, c.name])),
    }),
    [centers],
  );
  // Resolve exactly the supplier ids visible on this page — no 100-row
  // ceiling, no UUID fragments past it (P1-PORTAL-SCALE-001).
  const supplierNames = useSupplierNames(
    (page?.items ?? []).map((t) => t.supplier_id),
  );

  const currencies = Object.entries(summary?.payable_by_currency ?? {});
  const primary = currencies[0];

  const columns: Column<MilkTransaction>[] = [
    {
      key: "when",
      header: t("tx.collected"),
      cell: (tx) => (
        <div className="flex flex-col">
          <Link
            className="font-medium hover:underline"
            href={`/transactions/${tx.id}`}
          >
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
      header: t("entity.supplier"),
      cell: (tx) =>
        tx.supplier_id ? (
          <Link
            className="hover:underline"
            href={`/suppliers/${tx.supplier_id}`}
          >
            {supplierNames[tx.supplier_id] ??
              `${tx.supplier_id.slice(0, 8)}…`}
          </Link>
        ) : (
          <span className="text-muted-foreground">
            {t("tx.notIdentified")}
          </span>
        ),
    },
    {
      key: "center",
      header: t("tx.centre"),
      secondary: true,
      cell: (tx) => (
        <Link className="hover:underline" href={`/centers/${tx.center_id}`}>
          {names.centers[tx.center_id] ?? `${tx.center_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    {
      // Quantity and quality belong together: the quality is WHY that quantity
      // earned the rate it did, and eleven separate columns clipped the last
      // one off a 1440px screen — which is the width the demonstration runs at.
      key: "quantity",
      header: t("field.quantity"),
      align: "end",
      cell: (tx) => (
        <div className="flex flex-col items-end">
          <Quantity value={tx.net_weight} unit={tx.weight_unit ?? "kg"} />
          <span className="text-xs tabular-nums text-muted-foreground">
            {tx.fat != null ? t("tx.fatShort", { fat: tx.fat }) : "—"}
            {tx.snf != null ? ` · ${t("tx.snfShort", { snf: tx.snf })}` : ""}
          </span>
        </div>
      ),
    },
    {
      // Likewise the rate is the operand that produced the value. Both are
      // printed exactly as the platform sent them.
      key: "value",
      header: t("delivery.value"),
      align: "end",
      cell: (tx) => (
        <div className="flex flex-col items-end">
          <Money amount={tx.gross_amount} currency={tx.currency} />
          <span className="text-xs tabular-nums text-muted-foreground">
            {tx.unit_price != null
              ? t("tx.atRate", { rate: String(tx.unit_price) })
              : t("tx.notPriced")}
          </span>
        </div>
      ),
    },
    {
      key: "state",
      header: t("field.status"),
      cell: (tx) => <StatusBadge status={tx.state} />,
    },
    {
      key: "settlement",
      header: t("entity.settlement"),
      cell: (tx) => {
        const s = status[tx.id];
        if (!s?.settlement_id)
          return (
            <span className="text-xs text-muted-foreground">
              {t("tx.notSettled")}
            </span>
          );
        return (
          <div className="flex flex-col items-start gap-0.5">
            <Link
              className="text-sm hover:underline"
              href={`/settlements/${s.settlement_id}`}
            >
              {s.settlement_number}
            </Link>
            <StatusBadge status={s.settlement_status} />
          </div>
        );
      },
    },
    {
      key: "payment",
      header: t("entity.payment"),
      cell: (tx) => {
        const s = status[tx.id];
        if (!s?.payment_id)
          return (
            <span className="text-xs text-muted-foreground">
              {t("tx.notPaid")}
            </span>
          );
        return (
          <div className="flex flex-col items-start gap-0.5">
            <Link
              className="text-sm hover:underline"
              href={`/payments/${s.payment_id}`}
            >
              {s.payment_number}
            </Link>
            <StatusBadge status={s.payment_status} />
          </div>
        );
      },
    },
    {
      key: "activity",
      header: t("tx.lastActivity"),
      secondary: true,
      cell: (tx) => {
        const s = status[tx.id];
        if (!s?.last_event_type)
          return <span className="text-muted-foreground">—</span>;
        return (
          <div className="flex flex-col">
            <span className="text-sm tabular-nums">
              {stamp(s.last_event_at)}
            </span>
            <span className="text-xs text-muted-foreground">
              {humanise(s.last_event_type)}
            </span>
          </div>
        );
      },
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("tx.actions")}</span>,
      align: "end",
      cell: (tx) => (
        <Link
          href={`/transactions/${tx.id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          {t("tx.open")}
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[100rem] flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title={t("transaction.title")}
        description={t("tx.description")}
        actions={
          <Link
            href="/transactions/new"
            className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            <Plus aria-hidden className="me-1.5 size-4" />
            {t("tx.recordCollection")}
          </Link>
        }
      />

      <DateRangePicker value={range} onChange={setRange} busy={loading} />

      <section
        aria-label={t("tx.summaryAria")}
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <StatTile
          label={t("dashboard.collections")}
          value={summary ? summary.transactions : "—"}
          hint={
            summary
              ? t("tx.acceptedRejected", {
                  accepted: summary.accepted,
                  rejected: summary.rejected,
                })
              : undefined
          }
          icon={<Activity className="size-4" />}
        />
        <StatTile
          label={t("field.quantity")}
          value={
            summary ? (
              <Quantity value={summary.total_net_weight_kg} unit="kg" />
            ) : (
              "—"
            )
          }
          hint={
            summary
              ? t("tx.suppliersCount", { count: summary.suppliers_served })
              : undefined
          }
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label={t("delivery.value")}
          value={
            primary ? (
              <Money amount={primary[1]} currency={primary[0]} />
            ) : summary ? (
              <Money amount="0.00" currency={orgCurrency} />
            ) : (
              "—"
            )
          }
          icon={<Banknote className="size-4" />}
        />
        <StatTile
          label={t("dashboard.averageFat")}
          value={
            summary?.weighted_avg_fat != null
              ? `${summary.weighted_avg_fat}%`
              : "—"
          }
          hint={t("tx.weightedByQuantity")}
          icon={<Percent className="size-4" />}
        />
      </section>

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption={t("tx.caption")}
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(tx) => tx.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered ? t("tx.emptyFiltered") : t("tx.emptyPeriod"),
              description: filtered
                ? t("tx.emptyFilteredHint")
                : t("tx.emptyPeriodHint"),
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tx-state">{t("field.status")}</Label>
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
                        {s
                          ? s.toLowerCase().replace(/_/g, " ")
                          : t("tx.allStatuses")}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="tx-center">{t("tx.centre")}</Label>
                  <select
                    id="tx-center"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={centerId}
                    onChange={(e) => {
                      setCenterId(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">{t("tx.allCentres")}</option>
                    {centers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
                <EntityPicker
                  id="tx-supplier"
                  label={t("entity.supplier")}
                  placeholder={t("tx.allSuppliersSearch")}
                  value={supplierId}
                  valueLabel={supplierFilterLabel || undefined}
                  onSelect={(id, label) => {
                    setSupplierId(id);
                    setSupplierFilterLabel(label);
                    setOffset(0);
                  }}
                  search={async (q, off) => {
                    const p = await listSuppliers({
                      q: q || undefined,
                      limit: 20,
                      offset: off,
                    });
                    return {
                      items: (p.items ?? []).map((s) => ({
                        id: s.id,
                        label: s.full_name,
                        detail: s.code,
                      })),
                      total: p.total,
                    };
                  }}
                />
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
                    {t("tx.clearFilters")}
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
