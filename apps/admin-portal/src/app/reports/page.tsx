"use client";

import Link from "next/link";

import { useCallback, useEffect, useState } from "react";

import { useBusinessToday } from "@/components/date-range";
import { Pagination } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageContainer } from "@/components/page-container";
import { PageHeader } from "@/components/page-header";
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

const PAGE_SIZE = 50;

/** The platform's SummaryPage: one row type at a time, with its own total. */
type SummaryPageOf<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export default function ReportsPage() {
  // The DAIRY's today. `new Date().toISOString()` is UTC, so a Kenyan
  // cooperative after local midnight opened this report on yesterday and an
  // Indian one did for five and a half hours of every day (DEMO-019).
  //
  // DERIVED, not stored: the shell mounts this page before it knows which
  // organization is signed in, so a `useState` initializer would capture the
  // UTC fallback and keep it. The reader's own choice IS stored, because that
  // must survive — which is why these are two values and not one.
  const today = useBusinessToday();
  const [chosen, setChosen] = useState<{ from: string; to: string } | null>(
    null,
  );
  const dateFrom = chosen?.from ?? today;
  const dateTo = chosen?.to ?? today;
  const setDateFrom = (from: string) => setChosen({ from, to: dateTo });
  const setDateTo = (to: string) => setChosen({ from: dateFrom, to });
  const [centerId, setCenterId] = useState("");
  const [centers, setCenters] = useState<Center[]>([]);
  const [daily, setDaily] = useState<DailyCollectionSummary | null>(null);
  // P1-PORTAL-SCALE-001: the platform pages these summaries (ordered by milk
  // supplied, largest first) and its `total` is authoritative — the page no
  // longer shows the first 50 rows as if they were the whole dairy.
  const [centerPage, setCenterPage] =
    useState<SummaryPageOf<CenterSummaryRow> | null>(null);
  const [supplierPage, setSupplierPage] =
    useState<SummaryPageOf<SupplierSummaryRow> | null>(null);
  const [centerOffset, setCenterOffset] = useState(0);
  const [supplierOffset, setSupplierOffset] = useState(0);
  const [tableBusy, setTableBusy] = useState(false);
  const [settlements, setSettlements] = useState<SettlementReport | null>(null);
  const [pricing, setPricing] = useState<PricingReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const range = { date_from: dateFrom, date_to: dateTo };
    try {
      const [d, st, p] = await Promise.all([
        getDailyReport({ ...range, center_id: centerId || undefined }),
        getSettlementReport({ ...range, center_id: centerId || undefined }),
        getPricingReport({ ...range, center_id: centerId || undefined }),
      ]);
      setDaily(d);
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

  // A filter change starts both tables from their first page again —
  // deferred, as everywhere else, so the effect never renders synchronously.
  useEffect(() => {
    const t = setTimeout(() => {
      setCenterOffset(0);
      setSupplierOffset(0);
    }, 0);
    return () => clearTimeout(t);
  }, [dateFrom, dateTo, centerId]);

  useEffect(() => {
    const t = setTimeout(async () => {
      setTableBusy(true);
      try {
        const c = await getCenterReport({
          date_from: dateFrom,
          date_to: dateTo,
          limit: String(PAGE_SIZE),
          offset: String(centerOffset),
        });
        setCenterPage(c as SummaryPageOf<CenterSummaryRow>);
        setError(null);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.detail : "Failed to load reports",
        );
      } finally {
        setTableBusy(false);
      }
    }, 150);
    return () => clearTimeout(t);
  }, [dateFrom, dateTo, centerOffset]);

  useEffect(() => {
    const t = setTimeout(async () => {
      setTableBusy(true);
      try {
        const s = await getSupplierReport({
          date_from: dateFrom,
          date_to: dateTo,
          center_id: centerId || undefined,
          limit: String(PAGE_SIZE),
          offset: String(supplierOffset),
        });
        setSupplierPage(s as SummaryPageOf<SupplierSummaryRow>);
        setError(null);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.detail : "Failed to load reports",
        );
      } finally {
        setTableBusy(false);
      }
    }, 150);
    return () => clearTimeout(t);
  }, [dateFrom, dateTo, centerId, supplierOffset]);

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
    <PageContainer width="default">
      <PageHeader
        title="Reports"
        description="Operational insights from live procurement data"
      />

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
          <Label htmlFor="r-center">Centre</Label>
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
          {daily.in_progress > 0 &&
            `${daily.in_progress} transaction(s) still in progress.`}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Collection by center</CardTitle>
          <CardDescription>
            Ordered by milk supplied, largest first — the platform&apos;s own
            order, over the whole range.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Centre</TableHead>
                <TableHead className="text-end">Transactions</TableHead>
                <TableHead className="text-end">Accepted</TableHead>
                <TableHead className="text-end">Milk (kg)</TableHead>
                <TableHead className="text-end">Payable</TableHead>
                <TableHead className="text-end">Avg FAT</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(centerPage?.items ?? []).map((row) => (
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
                  <TableCell className="text-end">
                    {row.total_net_weight_kg}
                  </TableCell>
                  <TableCell className="text-end whitespace-nowrap">
                    <Money
                      amount={row.payable_amount}
                      currency={row.currency}
                    />
                  </TableCell>
                  <TableCell className="text-end">
                    {row.weighted_avg_fat ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
              {(centerPage?.items ?? []).length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-muted-foreground"
                  >
                    No collection recorded in this range.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {centerPage ? (
            <Pagination
              offset={centerOffset}
              limit={PAGE_SIZE}
              total={centerPage.total}
              busy={tableBusy}
              onChange={setCenterOffset}
            />
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Collection by supplier</CardTitle>
          <CardDescription>
            Ordered by milk supplied, largest first — every supplier in the
            range is here, page by page.
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
              {(supplierPage?.items ?? []).map((row) => (
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
                  <TableCell className="text-end">
                    {row.total_net_weight_kg}
                  </TableCell>
                  <TableCell className="text-end whitespace-nowrap">
                    <Money
                      amount={row.payable_amount}
                      currency={row.currency}
                    />
                  </TableCell>
                  <TableCell className="text-end">
                    {row.weighted_avg_fat ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
              {(supplierPage?.items ?? []).length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-muted-foreground"
                  >
                    No deliveries recorded in this range.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {supplierPage ? (
            <Pagination
              offset={supplierOffset}
              limit={PAGE_SIZE}
              total={supplierPage.total}
              busy={tableBusy}
              onChange={setSupplierOffset}
            />
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Settlements</CardTitle>
            <CardDescription>
              <Link
                className="text-primary hover:underline"
                href="/settlements"
              >
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
                  {settlements.total_settlements} settlement(s),{" "}
                  {settlements.total_lines} line(s)
                </p>
              </>
            ) : (
              <p className="text-muted-foreground">
                No settlements in this range.
              </p>
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
                    {pricing.priced_transactions} /{" "}
                    {pricing.unpriced_transactions}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Unit price (min · avg · max)</span>
                  <span>
                    {String(pricing.min_unit_price ?? "—")} ·{" "}
                    {pricing.avg_unit_price ?? "—"} ·{" "}
                    {String(pricing.max_unit_price ?? "—")}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Gross priced</span>
                  <span>
                    {Object.entries(pricing.gross_by_currency)
                      .map(
                        ([currency, amount]) =>
                          `${formatAmount(amount)} ${currency}`,
                      )
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
    </PageContainer>
  );
}
