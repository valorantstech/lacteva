"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Clock, Droplets } from "lucide-react";
import {
  ApiError,
  type CenterDetail,
  type CollectionTrend,
  type DailyCollectionSummary,
  type MilkTransactionPage,
  type ReadinessResult,
  type ReportPage,
  type SettlementReport,
  type SupplierSummaryRow,
  getCenterDetail,
  getCollectionTrend,
  getDailyReport,
  getReadiness,
  getSettlementReport,
  getSupplierReport,
  listMilkTransactions,
} from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type DateRange, DateRangePicker, resolveRange } from "@/components/date-range";
import { BarBreakdown, TrendChart } from "@/components/trend-chart";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState, TableSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { useLocale } from "@/lib/i18n";

/**
 * One collection centre (DEMO-003).
 *
 * Every panel is an existing platform contract, filtered to this centre —
 * `daily`, `trend`, `by-supplier` and `settlements` all already accept a
 * `center_id`, so nothing new was invented to fill a screen. Each loads
 * independently, so a slow report costs its own card.
 *
 * READINESS is the point of this page. It is the platform's own evaluation,
 * check by check, with the reason each one failed — not a green badge inferred
 * from the record existing. A centre that cannot take milk must say why.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;
const describe = (e: unknown) =>
  e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "the request failed";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export default function CenterDetailPage({ params }: { params: Promise<{ id: string }> }) {
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const { currency: orgCurrency } = useLocale();
  const { id } = use(params);
  const [range, setRange] = useState<DateRange>(() => resolveRange("30d"));

  const [detail, setDetail] = useState<Load<CenterDetail>>(LOADING);
  const [readiness, setReadiness] = useState<Load<ReadinessResult>>(LOADING);
  const [summary, setSummary] = useState<Load<DailyCollectionSummary>>(LOADING);
  const [trend, setTrend] = useState<Load<CollectionTrend>>(LOADING);
  const [suppliers, setSuppliers] = useState<Load<ReportPage<SupplierSummaryRow>>>(LOADING);
  const [recent, setRecent] = useState<Load<MilkTransactionPage>>(LOADING);
  const [settlements, setSettlements] = useState<Load<SettlementReport>>(LOADING);

  const load = useCallback(
    async (window: DateRange) => {
      const params = { date_from: window.from, date_to: window.to, center_id: id };
      const ok =
        <T,>(set: (v: Load<T>) => void) =>
        (data: T) =>
          set({ state: "ready", data });
      const fail =
        <T,>(set: (v: Load<T>) => void) =>
        (e: unknown) =>
          set({ state: "error", message: describe(e) });

      await Promise.allSettled([
        getCenterDetail(id).then(ok(setDetail), fail(setDetail)),
        getReadiness(id).then(ok(setReadiness), fail(setReadiness)),
        getDailyReport(params).then(ok(setSummary), fail(setSummary)),
        getCollectionTrend(params).then(ok(setTrend), fail(setTrend)),
        getSupplierReport({ ...params, limit: "6" }).then(ok(setSuppliers), fail(setSuppliers)),
        listMilkTransactions({ center_id: id, limit: 8, offset: 0 }).then(
          ok(setRecent),
          fail(setRecent),
        ),
        getSettlementReport({ center_id: id }).then(ok(setSettlements), fail(setSettlements)),
      ]);
    },
    [id],
  );

  useEffect(() => {
    const t = setTimeout(() => void load(range), 0);
    return () => clearTimeout(t);
  }, [load, range]);

  const center = detail.state === "ready" ? detail.data.center : null;
  const stats = summary.state === "ready" ? summary.data : null;
  const currencies = Object.entries(stats?.payable_by_currency ?? {});
  const primary = currencies[0];

  if (detail.state === "error") {
    return (
      <div className="mx-auto w-full max-w-3xl p-8">
        <ErrorState message={`This centre could not be loaded — ${detail.message}.`} />
        <p className="mt-4 text-sm">
          <Link className="underline underline-offset-4" href="/centers">
            Back to collection centres
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[{ label: "Centres", href: "/centers" }, { label: center?.name ?? "Centre" }]}
        title={center?.name ?? "Collection centre"}
        description={
          center
            ? `${center.code} · ${center.timezone}`
            : "Loading this centre's details…"
        }
        actions={center ? <StatusBadge status={center.status} /> : undefined}
      />

      <DateRangePicker value={range} onChange={setRange} />

      <section aria-label="Centre statistics" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Collections"
          value={stats ? stats.transactions : "—"}
          hint={stats ? `${stats.accepted} accepted · ${stats.rejected} rejected` : undefined}
        />
        <StatTile
          label="Quantity"
          value={stats ? <Quantity value={stats.total_net_weight_kg} unit="kg" /> : "—"}
          hint={stats ? `${stats.suppliers_served} suppliers served` : undefined}
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label="Collection value"
          value={primary ? <Money amount={primary[1]} currency={primary[0]} /> : stats ? <Money amount="0.00" currency={orgCurrency} /> : "—"}
          hint="payable in this period"
        />
        <StatTile
          label="Average fat"
          value={stats?.weighted_avg_fat != null ? `${stats.weighted_avg_fat}%` : "—"}
          hint="weighted by quantity"
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Readiness</CardTitle>
            <CardDescription>
              Whether this centre can receive milk right now, evaluated by the platform.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {readiness.state === "loading" ? (
              <LoadingState label="Evaluating readiness…" />
            ) : readiness.state === "error" ? (
              <ErrorState message={`Readiness is unavailable — ${readiness.message}.`} />
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <StatusBadge status={readiness.data.status} />
                  <span className="text-xs text-muted-foreground">
                    checked {String(readiness.data.evaluated_at).slice(0, 19).replace("T", " ")}
                  </span>
                </div>
                {(readiness.data.checks ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No readiness rules reported.</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {(readiness.data.checks ?? []).map((check) => (
                      <li key={check.rule} className="flex items-start gap-2.5 text-sm">
                        {check.passed ? (
                          <CheckCircle2
                            aria-hidden
                            className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                          />
                        ) : (
                          <AlertTriangle
                            aria-hidden
                            className={
                              check.severity === "blocking"
                                ? "mt-0.5 size-4 shrink-0 text-destructive"
                                : "mt-0.5 size-4 shrink-0 text-muted-foreground"
                            }
                          />
                        )}
                        <span className="flex flex-col">
                          <span className={check.passed ? "" : "font-medium"}>
                            {check.rule.replace(/[_.]/g, " ")}
                          </span>
                          {/* The platform's own reason. A centre that cannot
                              take milk must say WHY, not merely that it cannot. */}
                          {!check.passed && check.detail ? (
                            <span className="text-muted-foreground">{check.detail}</span>
                          ) : null}
                        </span>
                        <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                          {check.passed ? "pass" : check.severity}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock aria-hidden className="size-4 text-muted-foreground" />
              Operating hours
            </CardTitle>
            <CardDescription>Interpreted in {center?.timezone ?? "the centre's timezone"}.</CardDescription>
          </CardHeader>
          <CardContent>
            {detail.state === "loading" ? (
              <LoadingState label="Loading hours…" />
            ) : (detail.data.operating_windows ?? []).length === 0 ? (
              <EmptyState
                title="No operating hours set"
                description="A centre without operating hours cannot open a collection session."
              />
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm">
                {(detail.data.operating_windows ?? [])
                  .slice()
                  .sort((a, b) => a.day_of_week - b.day_of_week)
                  .map((w) => (
                    <li key={`${w.day_of_week}-${w.opens}`} className="flex justify-between gap-4">
                      <span className="text-muted-foreground">
                        {DAYS[w.day_of_week] ?? `Day ${w.day_of_week}`}
                      </span>
                      <span className="tabular-nums">
                        {w.opens} – {w.closes}
                      </span>
                    </li>
                  ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Quantity collected</CardTitle>
          <CardDescription>
            {range.from} to {range.to}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trend.state === "loading" ? (
            <LoadingState label="Loading the trend…" />
          ) : trend.state === "error" ? (
            <ErrorState message={`The trend is unavailable — ${trend.message}.`} />
          ) : (
            <TrendChart
              metric="quantity"
              data={(trend.data.points ?? []).map((p) => ({
                day: p.day,
                quantity: p.total_net_weight_kg,
                value: String(p.payable_amount),
                currency: p.currency,
                transactions: p.transactions,
              }))}
            />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Suppliers delivering here</CardTitle>
            <CardDescription>By quantity over the selected range.</CardDescription>
          </CardHeader>
          <CardContent>
            {suppliers.state === "loading" ? (
              <TableSkeleton rows={4} columns={3} />
            ) : suppliers.state === "error" ? (
              <ErrorState message={`Unavailable — ${suppliers.message}.`} />
            ) : (
              <BarBreakdown
                emptyTitle="No supplier deliveries in this period"
                rows={(suppliers.data.items ?? []).map((row) => ({
                  key: row.supplier_id,
                  label: row.supplier_name,
                  magnitude: row.total_net_weight_kg,
                  detail: (
                    <span className="flex items-center gap-2">
                      <Quantity value={row.total_net_weight_kg} unit="kg" />
                      <Money amount={row.payable_amount} currency={row.currency} />
                    </span>
                  ),
                }))}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Settlements</CardTitle>
            <CardDescription>Raised against this centre.</CardDescription>
          </CardHeader>
          <CardContent>
            {settlements.state === "loading" ? (
              <LoadingState label="Loading settlements…" />
            ) : settlements.state === "error" ? (
              <ErrorState message={`Unavailable — ${settlements.message}.`} />
            ) : (settlements.data.by_status ?? []).length === 0 ? (
              <EmptyState title="No settlements for this centre yet" />
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  {(settlements.data.by_status ?? []).map((row) => (
                    <span key={row.status} className="flex items-center gap-1.5">
                      <StatusBadge status={row.status} />
                      <span className="text-sm tabular-nums text-muted-foreground">
                        {row.count}
                      </span>
                    </span>
                  ))}
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Finalized net total</dt>
                    <dd className="mt-0.5">
                      <Money amount={settlements.data.finalized_net_total} emphasis />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Settlement lines</dt>
                    <dd className="mt-0.5 tabular-nums">{settlements.data.total_lines ?? 0}</dd>
                  </div>
                </dl>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent collections</CardTitle>
          <CardDescription>The most recent transactions at this centre.</CardDescription>
        </CardHeader>
        <CardContent>
          {recent.state === "loading" ? (
            <TableSkeleton rows={5} columns={4} />
          ) : recent.state === "error" ? (
            <ErrorState message={`Unavailable — ${recent.message}.`} />
          ) : (recent.data.items ?? []).length === 0 ? (
            <EmptyState
              title="No collections yet"
              description="Open a session at this centre to begin receiving milk."
            />
          ) : (
            <div className="w-full overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Recent collections at this centre</caption>
                <thead>
                  <tr className="border-b border-border text-start text-muted-foreground">
                    <th scope="col" className="py-2 font-medium">State</th>
                    <th scope="col" className="py-2 font-medium">Milk</th>
                    <th scope="col" className="py-2 text-end font-medium">Net</th>
                    <th scope="col" className="py-2 text-end font-medium">Rate</th>
                    <th scope="col" className="py-2 text-end font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(recent.data.items ?? []).map((tx) => (
                    <tr key={tx.id} className="border-b border-border/60 last:border-0">
                      <td className="py-2">
                        <StatusBadge status={tx.state} />
                      </td>
                      <td className="py-2 text-muted-foreground">{tx.milk_type ?? "—"}</td>
                      <td className="py-2 text-end">
                        <Quantity value={tx.net_weight} unit="kg" />
                      </td>
                      <td className="py-2 text-end tabular-nums text-muted-foreground">
                        {tx.unit_price ?? "—"}
                      </td>
                      <td className="py-2 text-end">
                        <Money amount={tx.gross_amount} currency={tx.currency} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
