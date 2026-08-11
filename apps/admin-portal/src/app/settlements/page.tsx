"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Banknote, FileText, Lock, Plus } from "lucide-react";
import {
  ApiError,
  type Center,
  type Settlement,
  type SettlementPageResult,
  type SettlementReport,
  type Supplier,
  createSettlement,
  getSettlementReport,
  listCenters,
  listSettlements,
  listSuppliers,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { Money } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

/**
 * Settlements (DEMO-006).
 *
 * What a settlement IS: the periodic statement of what one supplier is owed by
 * one centre — the collections of that window, summed by the platform, frozen
 * when finalized. It is the bridge between collection and payment, and it is
 * the first screen in this portal where a wrong number is a wrong payment.
 *
 * So the same two rules as everywhere else, restated because money makes them
 * matter more:
 *
 * 1. EVERY FILTER IS A QUERY PARAMETER. Search, status, supplier and centre are
 *    applied by the database, over the whole table, not over the visible page.
 *    The page this replaced counted statuses by looping over the ten rows it
 *    happened to be showing — a number that was wrong the moment a second page
 *    existed.
 * 2. THE KPI ROW IS THE PLATFORM'S OWN AGGREGATE. `/v1/reports/settlements`
 *    already groups by status and totals the finalized net. The portal adds
 *    nothing up.
 */

const PAGE_SIZE = 15;

/** The real lifecycle. A settlement is never in any other status. */
const STATUSES = ["", "draft", "calculated", "finalized", "cancelled"] as const;

/** The business reason when the platform gave one, the HTTP detail otherwise. */
const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Request failed";
};

export default function SettlementsPage() {
  const [page, setPage] = useState<SettlementPageResult | null>(null);
  const [report, setReport] = useState<SettlementReport | null>(null);
  const [centers, setCenters] = useState<Center[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const [q, setQ] = useState("");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("");
  const [centerId, setCenterId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const filtered = Boolean(q || status || centerId || supplierId);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listSettlements({
          q: q || undefined,
          status: status || undefined,
          supplier_id: supplierId || undefined,
          center_id: centerId || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
      // A reporting hiccup must not blank the table.
      getSettlementReport({
        supplier_id: supplierId || undefined,
        center_id: centerId || undefined,
      })
        .then(setReport)
        .catch(() => setReport(null));
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [centerId, offset, q, status, supplierId]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 150);
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

  const byStatus = (name: string) =>
    report?.by_status?.find((r) => r.status === name)?.count ?? 0;

  const columns: Column<Settlement>[] = [
    {
      key: "number",
      header: "Settlement",
      cell: (s) => (
        <div className="flex flex-col">
          <Link className="font-medium hover:underline" href={`/settlements/${s.id}`}>
            {s.settlement_number}
          </Link>
          <span className="text-xs text-muted-foreground">
            {s.line_count} {s.line_count === 1 ? "collection" : "collections"}
          </span>
        </div>
      ),
    },
    {
      key: "supplier",
      header: "Supplier",
      cell: (s) => (
        <Link className="hover:underline" href={`/suppliers/${s.supplier_id}`}>
          {names.suppliers[s.supplier_id] ?? `${s.supplier_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    {
      key: "center",
      header: "Centre",
      secondary: true,
      cell: (s) => (
        <Link className="hover:underline" href={`/centers/${s.center_id}`}>
          {names.centers[s.center_id] ?? `${s.center_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    {
      key: "period",
      header: "Period",
      secondary: true,
      cell: (s) => (
        <span className="tabular-nums text-sm">
          {s.period_from} → {s.period_to}
        </span>
      ),
    },
    {
      key: "net",
      header: "Net payable",
      align: "end",
      cell: (s) => <Money amount={s.net_amount} currency={s.currency} />,
    },
    {
      key: "status",
      header: "Status",
      cell: (s) => (
        <span className="inline-flex items-center gap-1.5">
          <StatusBadge status={s.status} />
          {s.status === "finalized" ? (
            <Lock aria-label="immutable" className="size-3 text-muted-foreground" />
          ) : null}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (s) => (
        <Link
          href={`/settlements/${s.id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          Open
        </Link>
      ),
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Settlements"
        description="What each supplier is owed for a period — the collections of that window, summed by the platform."
        actions={
          <Button type="button" onClick={() => setShowCreate((v) => !v)}>
            <Plus aria-hidden className="mr-1.5 size-4" />
            New settlement
          </Button>
        }
      />

      <section aria-label="Settlement summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Settlements"
          value={report ? report.total_settlements : "—"}
          hint={report ? `${report.total_lines} collections settled` : undefined}
          icon={<FileText className="size-4" />}
        />
        <StatTile
          label="Open"
          value={report ? byStatus("draft") + byStatus("calculated") : "—"}
          hint={report ? `${byStatus("draft")} draft · ${byStatus("calculated")} calculated` : undefined}
        />
        <StatTile
          label="Finalized"
          value={report ? byStatus("finalized") : "—"}
          hint="immutable once finalized"
          icon={<Lock className="size-4" />}
        />
        <StatTile
          label="Finalized value"
          value={report ? <Money amount={report.finalized_net_total} currency="KES" /> : "—"}
          icon={<Banknote className="size-4" />}
        />
      </section>

      {showCreate ? (
        <CreateSettlementCard
          centers={centers}
          suppliers={suppliers}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            setOffset(0);
            void load();
          }}
        />
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Supplier settlements in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(s) => s.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered ? "No settlement matches these filters" : "No settlements yet",
              description: filtered
                ? "Try a different status, or clear the filters."
                : "Create a settlement for a supplier and period, then collect its completed collections.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="st-q">Search</Label>
                  <Input
                    id="st-q"
                    className="h-9 w-52"
                    placeholder="Settlement number"
                    value={q}
                    onChange={(e) => {
                      setQ(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="st-status">Status</Label>
                  <select
                    id="st-status"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value as (typeof STATUSES)[number]);
                      setOffset(0);
                    }}
                  >
                    {STATUSES.map((s) => (
                      <option key={s || "all"} value={s}>
                        {s || "All statuses"}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="st-center">Centre</Label>
                  <select
                    id="st-center"
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
                  <Label htmlFor="st-supplier">Supplier</Label>
                  <select
                    id="st-supplier"
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
                      setQ("");
                      setStatus("");
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

/**
 * Opening a settlement period.
 *
 * BR-0009 forbids overlapping periods for the same supplier; adjacent ones are
 * fine. The portal does not try to predict that — it submits, and shows the
 * platform's refusal verbatim when it comes.
 */
function CreateSettlementCard({
  centers,
  suppliers,
  onClose,
  onCreated,
}: {
  centers: Center[];
  suppliers: Supplier[];
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [supplier, setSupplier] = useState("");
  const [center, setCenter] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [currency, setCurrency] = useState("KES");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createSettlement({
        supplier_id: supplier,
        center_id: center,
        period_from: from,
        period_to: to,
        currency,
      });
      onCreated(created.id);
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New settlement</CardTitle>
        <CardDescription>
          One supplier, one centre, one period. Periods for a supplier may not overlap (BR-0009).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ns-supplier">Supplier</Label>
              <select
                id="ns-supplier"
                required
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={supplier}
                onChange={(e) => setSupplier(e.target.value)}
              >
                <option value="">Select…</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ns-center">Centre</Label>
              <select
                id="ns-center"
                required
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={center}
                onChange={(e) => setCenter(e.target.value)}
              >
                <option value="">Select…</option>
                {centers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ns-from">Period from</Label>
              <Input
                id="ns-from"
                type="date"
                required
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ns-to">Period to</Label>
              <Input
                id="ns-to"
                type="date"
                required
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ns-currency">Currency</Label>
              <Input
                id="ns-currency"
                required
                maxLength={3}
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              />
            </div>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create settlement"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
