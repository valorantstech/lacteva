"use client";

import Link from "next/link";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Money, formatAmount } from "@/components/money";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  Center,
  CenterSummaryRow,
  DailyCollectionSummary,
  PricingReport,
  SettlementReport,
  SupplierSummaryRow,
  getCenterReport,
  getDailyReport,
  getPricingReport,
  getSettlementReport,
  getSupplierReport,
  listCenters,
} from "@/lib/api";

type SortKey = "weight" | "payable" | "count";

const bySort = <T extends { total_net_weight_kg: number; payable_amount: string | number }>(
  rows: T[],
  key: SortKey,
  count: (row: T) => number,
) =>
  [...rows].sort((a, b) =>
    key === "weight"
      ? b.total_net_weight_kg - a.total_net_weight_kg
      : key === "payable"
        ? Number(b.payable_amount) - Number(a.payable_amount)
        : count(b) - count(a),
  );

export default function ReportsPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  const [centerId, setCenterId] = useState("");
  const [centers, setCenters] = useState<Center[]>([]);
  const [daily, setDaily] = useState<DailyCollectionSummary | null>(null);
  const [centerRows, setCenterRows] = useState<CenterSummaryRow[]>([]);
  const [supplierRows, setSupplierRows] = useState<SupplierSummaryRow[]>([]);
  const [settlements, setSettlements] = useState<SettlementReport | null>(null);
  const [pricing, setPricing] = useState<PricingReport | null>(null);
  const [centerSort, setCenterSort] = useState<SortKey>("weight");
  const [supplierSort, setSupplierSort] = useState<SortKey>("weight");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const range = { date_from: dateFrom, date_to: dateTo };
    try {
      const [d, c, s, st, p] = await Promise.all([
        getDailyReport({ ...range, center_id: centerId || undefined }),
        getCenterReport({ ...range, limit: "50", offset: "0" }),
        getSupplierReport({
          ...range,
          center_id: centerId || undefined,
          limit: "50",
          offset: "0",
        }),
        getSettlementReport({ ...range, center_id: centerId || undefined }),
        getPricingReport({ ...range, center_id: centerId || undefined }),
      ]);
      setDaily(d);
      setCenterRows(c.items as CenterSummaryRow[]);
      setSupplierRows(s.items as SupplierSummaryRow[]);
      setSettlements(st);
      setPricing(p);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load reports");
    }
  }, [dateFrom, dateTo, centerId]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      listCenters({ limit: 100, offset: 0 })
        .then((p) => setCenters(p.items))
        .catch(() => setCenters([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  const payable = daily
    ? Object.entries(daily.payable_by_currency)
        // DEMO-010: through the shared formatter, so this page groups its
        // digits like every other one. It read `13860.00 KES` beside
        // `13,860.00 KES` elsewhere, which during a demonstration looks like
        // two different systems rather than one.
        .map(([currency, amount]) => `${formatAmount(amount)} ${currency}`)
        .join(" · ") || "0"
    : "…";

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">
          Operational insights from live procurement data
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="r-from">From</Label>
          <Input
            id="r-from"
            type="date"
            className="h-8"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="r-to">To</Label>
          <Input
            id="r-to"
            type="date"
            className="h-8"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="r-center">Center</Label>
          <select
            id="r-center"
            className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
            value={centerId}
            onChange={(e) => setCenterId(e.target.value)}
          >
            <option value="">All centers</option>
            {centers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
        </div>
        <Button size="sm" variant="outline" onClick={() => void refresh()}>
          Refresh
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {daily && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(
            [
              ["Milk collected", `${daily.total_net_weight_kg} kg`],
              ["Payable", payable],
              [
                "Transactions",
                `${daily.transactions} (${daily.accepted}✓ / ${daily.rejected}✗)`,
              ],
              [
                "Avg FAT / SNF",
                `${daily.weighted_avg_fat ?? "—"} / ${daily.weighted_avg_snf ?? "—"}`,
              ],
            ] as const
          ).map(([label, value]) => (
            <Card key={label}>
              <CardContent className="pt-4">
                <p className="text-xl font-semibold">{value}</p>
                <p className="text-xs text-muted-foreground">{label}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {daily && (daily.unpriced_accepted > 0 || daily.in_progress > 0) && (
        <p className="text-sm text-amber-600 dark:text-amber-500">
          {daily.unpriced_accepted > 0 &&
            `${daily.unpriced_accepted} accepted transaction(s) without pricing. `}
          {daily.in_progress > 0 && `${daily.in_progress} transaction(s) still in progress.`}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Collection by center</CardTitle>
          <CardDescription>
            Sorted by{" "}
            {(["weight", "payable", "count"] as const).map((key) => (
              <button
                key={key}
                className={`me-2 underline-offset-4 ${centerSort === key ? "font-semibold underline" : "hover:underline"}`}
                onClick={() => setCenterSort(key)}
              >
                {key}
              </button>
            ))}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Center</TableHead>
                <TableHead className="text-end">Transactions</TableHead>
                <TableHead className="text-end">Accepted</TableHead>
                <TableHead className="text-end">Milk (kg)</TableHead>
                <TableHead className="text-end">Payable</TableHead>
                <TableHead className="text-end">Avg FAT</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bySort(centerRows, centerSort, (r) => r.transactions).map((row) => (
                <TableRow key={row.center_id}>
                  <TableCell>
                    <Link
                      className="text-primary hover:underline"
                      href={`/centers/${row.center_id}`}
                    >
                      {row.center_code} — {row.center_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-end">{row.transactions}</TableCell>
                  <TableCell className="text-end">{row.accepted}</TableCell>
                  <TableCell className="text-end">{row.total_net_weight_kg}</TableCell>
                  <TableCell className="text-end whitespace-nowrap">
                    <Money amount={row.payable_amount} currency={row.currency} />
                  </TableCell>
                  <TableCell className="text-end">{row.weighted_avg_fat ?? "—"}</TableCell>
                </TableRow>
              ))}
              {centerRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    No collection recorded in this range.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Collection by supplier</CardTitle>
          <CardDescription>
            Sorted by{" "}
            {(["weight", "payable", "count"] as const).map((key) => (
              <button
                key={key}
                className={`me-2 underline-offset-4 ${supplierSort === key ? "font-semibold underline" : "hover:underline"}`}
                onClick={() => setSupplierSort(key)}
              >
                {key}
              </button>
            ))}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Supplier</TableHead>
                <TableHead className="text-end">Deliveries</TableHead>
                <TableHead className="text-end">Accepted</TableHead>
                <TableHead className="text-end">Milk (kg)</TableHead>
                <TableHead className="text-end">Payable</TableHead>
                <TableHead className="text-end">Avg FAT</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bySort(supplierRows, supplierSort, (r) => r.deliveries).map((row) => (
                <TableRow key={row.supplier_id}>
                  <TableCell>
                    <Link
                      className="text-primary hover:underline"
                      href={`/suppliers/${row.supplier_id}`}
                    >
                      {row.supplier_code} — {row.supplier_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-end">{row.deliveries}</TableCell>
                  <TableCell className="text-end">{row.accepted}</TableCell>
                  <TableCell className="text-end">{row.total_net_weight_kg}</TableCell>
                  <TableCell className="text-end whitespace-nowrap">
                    <Money amount={row.payable_amount} currency={row.currency} />
                  </TableCell>
                  <TableCell className="text-end">{row.weighted_avg_fat ?? "—"}</TableCell>
                </TableRow>
              ))}
              {supplierRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    No deliveries recorded in this range.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Settlements</CardTitle>
            <CardDescription>
              <Link className="text-primary hover:underline" href="/settlements">
                Open settlements →
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {settlements && settlements.by_status.length > 0 ? (
              <>
                {settlements.by_status.map((row) => (
                  <div key={row.status} className="flex justify-between">
                    <Badge variant="outline">{row.status}</Badge>
                    <span>
                      {row.count} · <Money amount={row.net_amount} />
                    </span>
                  </div>
                ))}
                <div className="flex justify-between border-t border-border pt-2 font-medium">
                  <span>Finalized total</span>
                  <Money amount={settlements.finalized_net_total} emphasis />
                </div>
                <p className="text-muted-foreground">
                  {settlements.total_settlements} settlement(s), {settlements.total_lines}{" "}
                  line(s)
                </p>
              </>
            ) : (
              <p className="text-muted-foreground">No settlements in this range.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pricing</CardTitle>
            <CardDescription>
              <Link className="text-primary hover:underline" href="/rate-cards">
                Open rate cards →
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {pricing ? (
              <>
                <div className="flex justify-between">
                  <span>Priced / unpriced transactions</span>
                  <span>
                    {pricing.priced_transactions} / {pricing.unpriced_transactions}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Unit price (min · avg · max)</span>
                  <span>
                    {String(pricing.min_unit_price ?? "—")} ·{" "}
                    {pricing.avg_unit_price ?? "—"} · {String(pricing.max_unit_price ?? "—")}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Gross priced</span>
                  <span>
                    {Object.entries(pricing.gross_by_currency)
                      .map(([currency, amount]) => `${formatAmount(amount)} ${currency}`)
                      .join(" · ") || "0"}
                  </span>
                </div>
                <div className="flex justify-between border-t border-border pt-2">
                  <span>Published cards / matrices / bands</span>
                  <span>
                    {pricing.published_rate_cards} / {pricing.active_matrices} /{" "}
                    {pricing.active_bands}
                  </span>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">Loading…</p>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
