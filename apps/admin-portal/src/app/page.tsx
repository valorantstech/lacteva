"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Banknote,
  Building2,
  CheckCircle2,
  Droplets,
  Handshake,
  Percent,
  Truck,
} from "lucide-react";
import {
  ApiError,
  type AuditRecord,
  type CenterSummaryRow,
  type CollectionTrend,
  type DashboardReport,
  type ReportPage,
  type Session,
  type SupplierSummaryRow,
  getCenterReport,
  getCollectionTrend,
  getDashboardReport,
  getSession,
  getSupplierReport,
  listAudit,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type DateRange, DateRangePicker, resolveRange } from "@/components/date-range";
import { BarBreakdown, TrendChart } from "@/components/trend-chart";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState, TableSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * The customer dashboard (DEMO-002).
 *
 * Two rules shape this file.
 *
 * 1. EVERY NUMBER COMES FROM THE PLATFORM. There is no counting of list
 *    endpoints and no arithmetic over money here — the aggregates live in
 *    `modules/reporting`, where the sums are exact `Decimal` inside the
 *    database. The date range is a QUERY PARAMETER, not a filter applied to
 *    rows that were fetched and then narrowed in the browser.
 *
 * 2. EACH REGION LOADS AND FAILS ON ITS OWN. Five independent requests, five
 *    independent states. A reporting endpoint that fails costs its own card and
 *    nothing else, because a dashboard that goes blank when one widget breaks
 *    tells an operator less than one that admits which part is missing.
 *
 * Every field read from a response is guarded (`?? []`, `?? {}`). DEMO-001
 * caught a real crash here — `by_status.map` on a body that had merely been
 * cast — and that lesson is cheap to keep and expensive to relearn.
 */

type Load<T> =
  | { state: "loading" }
  // DEMO-008: `forbidden` is not a failure. A collection operator has no
  // `reporting.read`, so every aggregate on this page 403s for them — and
  // rendering that as a wall of red errors tells them something broke when
  // the truth is that reporting is not part of their job.
  | { state: "forbidden" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;

/** Narrow an unknown failure into something an operator can read. */
function describe(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return error instanceof Error ? error.message : "the request failed";
}

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);
  const [range, setRange] = useState<DateRange>(() => resolveRange("7d"));
  const [metric, setMetric] = useState<"quantity" | "value">("quantity");

  const [dashboard, setDashboard] = useState<Load<DashboardReport>>(LOADING);
  const [trend, setTrend] = useState<Load<CollectionTrend>>(LOADING);
  const [centers, setCenters] = useState<Load<ReportPage<CenterSummaryRow>>>(LOADING);
  const [suppliers, setSuppliers] = useState<Load<ReportPage<SupplierSummaryRow>>>(LOADING);
  const [activity, setActivity] = useState<Load<AuditRecord[]>>(LOADING);
  const [busy, setBusy] = useState(false);

  const signedIn = session?.authenticated === true;

  useEffect(() => {
    let cancelled = false;
    getSession()
      .then((s) => !cancelled && setSession(s))
      .catch(() => !cancelled && setSession({ authenticated: false }))
      .finally(() => !cancelled && setChecked(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async (window: DateRange) => {
    setBusy(true);
    const params = { date_from: window.from, date_to: window.to };
    const ok =
      <T,>(set: (v: Load<T>) => void) =>
      (data: T) =>
        set({ state: "ready", data });
    const fail =
      <T,>(set: (v: Load<T>) => void) =>
      (e: unknown) =>
        set(
          e instanceof ApiError && e.status === 403
            ? { state: "forbidden" }
            : { state: "error", message: describe(e) },
        );

    // `allSettled`: one rejection must not cancel the others.
    await Promise.allSettled([
      getDashboardReport(params).then(ok(setDashboard), fail(setDashboard)),
      getCollectionTrend(params).then(ok(setTrend), fail(setTrend)),
      getCenterReport({ ...params, limit: "8" }).then(ok(setCenters), fail(setCenters)),
      getSupplierReport({ ...params, limit: "8" }).then(ok(setSuppliers), fail(setSuppliers)),
      listAudit({ limit: 12, offset: 0 })
        .then((r) => r.items)
        .then(ok(setActivity), fail(setActivity)),
    ]);
    setBusy(false);
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    const initial = setTimeout(() => void load(range), 0);
    return () => clearTimeout(initial);
  }, [load, range, signedIn]);

  if (!checked) {
    return (
      <div className="p-8">
        <LoadingState label="Checking your session…" />
      </div>
    );
  }

  if (!signedIn) {
    return (
      <div className="mx-auto w-full max-w-3xl p-8">
        <EmptyState
          title="Sign in to see today's collection"
          description="The dashboard reports on the organization you are signed in to."
          action={
            <a
              href="/login"
              className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              Sign in
            </a>
          }
        />
      </div>
    );
  }

  const report = dashboard.state === "ready" ? dashboard.data : null;
  const collection = report?.collection;
  const payments = report?.payments;
  const currencies = Object.entries(collection?.payable_by_currency ?? {});
  const primary = currencies[0];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Dashboard"
        description="Collection, settlement and payment across this organization — every figure computed by the platform."
        actions={
          <Button type="button" variant="outline" disabled={busy} onClick={() => void load(range)}>
            {busy ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />

      <DateRangePicker value={range} onChange={setRange} busy={busy} />

      {dashboard.state === "forbidden" ? (
        <Card>
          <CardContent className="flex flex-col gap-2 pt-6">
            <p className="font-medium">Reporting is not part of your access.</p>
            <p className="text-sm text-muted-foreground">
              The figures on this page come from the platform&apos;s reporting module, which your
              role does not include. Everything you do have access to is in the navigation on the
              left — nothing here is broken.
            </p>
          </CardContent>
        </Card>
      ) : dashboard.state === "error" ? (
        <ErrorState
          message={`The summary could not be loaded — ${dashboard.message}. The sections below load separately and may still be available.`}
          action={
            <Button type="button" size="sm" variant="outline" onClick={() => void load(range)}>
              Try again
            </Button>
          }
        />
      ) : null}

      <section aria-label="Collection summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatTile
          label="Collections"
          value={collection ? collection.transactions : "—"}
          hint={
            collection
              ? `${collection.accepted} accepted · ${collection.rejected} rejected`
              : undefined
          }
          icon={<Activity className="size-4" />}
        />
        <StatTile
          label="Quantity"
          value={collection ? <Quantity value={collection.total_net_weight_kg} unit="kg" /> : "—"}
          hint={collection ? `${collection.suppliers_served} suppliers served` : undefined}
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label="Collection value"
          value={
            primary ? (
              <Money amount={primary[1]} currency={primary[0]} />
            ) : collection ? (
              <Money amount="0.00" currency="KES" />
            ) : (
              "—"
            )
          }
          hint={currencies.length > 1 ? `+${currencies.length - 1} more currency` : "payable"}
          icon={<Banknote className="size-4" />}
        />
        <StatTile
          label="Average fat"
          value={collection?.weighted_avg_fat != null ? `${collection.weighted_avg_fat}%` : "—"}
          hint="weighted by quantity"
          icon={<Percent className="size-4" />}
        />
        <StatTile
          label="Active suppliers"
          value={report ? report.active_suppliers : "—"}
          hint="registered and active"
          icon={<Truck className="size-4" />}
        />
        <StatTile
          label="Active centres"
          value={report ? report.active_centers : "—"}
          hint={report?.inactive_centers ? `${report.inactive_centers} not active` : "all active"}
          icon={<Building2 className="size-4" />}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle aria-hidden className="size-4 text-muted-foreground" />
            Needs attention
          </CardTitle>
        </CardHeader>
        <CardContent>
          {dashboard.state === "loading" ? (
            <LoadingState label="Checking for exceptions…" />
          ) : !report ? (
            <p className="text-sm text-muted-foreground">Unavailable.</p>
          ) : (report.attention ?? []).length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 aria-hidden className="size-4" />
              No action required.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {(report.attention ?? []).map((item) => (
                <li key={item.key} className="flex items-center gap-3 text-sm">
                  <StatusBadge status={item.severity === "critical" ? "failed" : "pending"} />
                  <span className="font-medium tabular-nums">{item.count}</span>
                  <span className="text-muted-foreground">{item.label}</span>
                  {item.href ? (
                    <a
                      className="ml-auto text-xs underline-offset-4 hover:underline"
                      href={item.href}
                    >
                      review
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Collection trend</CardTitle>
            <CardDescription>
              {range.from} to {range.to}
            </CardDescription>
          </div>
          <div
            role="group"
            aria-label="Trend metric"
            className="flex gap-1 rounded-lg border border-border p-1"
          >
            {(["quantity", "value"] as const).map((m) => (
              <Button
                key={m}
                type="button"
                size="sm"
                variant={metric === m ? "secondary" : "ghost"}
                aria-pressed={metric === m}
                onClick={() => setMetric(m)}
              >
                {m === "quantity" ? "Quantity" : "Value"}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {trend.state === "loading" ? (
            <LoadingState label="Loading the trend…" />
          ) : trend.state === "forbidden" ? (
            <EmptyState
              title="Not part of your access"
              description="Your role does not include reporting. Nothing here is broken."
            />
          ) : trend.state === "error" ? (
            <ErrorState message={`The trend is unavailable — ${trend.message}.`} />
          ) : (
            <TrendChart
              metric={metric}
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
            <CardTitle className="flex items-center gap-2 text-base">
              <Handshake aria-hidden className="size-4 text-muted-foreground" />
              Settlements and payments
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {dashboard.state === "loading" ? (
              <LoadingState label="Loading money…" />
            ) : !report || !payments ? (
              <p className="text-sm text-muted-foreground">Unavailable.</p>
            ) : (
              <>
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Settlements
                  </p>
                  {(report.settlements?.by_status ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No settlements yet.</p>
                  ) : (
                    <div className="flex flex-wrap items-center gap-2">
                      {(report.settlements?.by_status ?? []).map((row) => (
                        <span key={row.status} className="flex items-center gap-1.5">
                          <StatusBadge status={row.status} />
                          <span className="text-sm tabular-nums text-muted-foreground">
                            {row.count}
                          </span>
                        </span>
                      ))}
                    </div>
                  )}
                  <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt className="text-muted-foreground">Finalized net total</dt>
                      <dd className="mt-0.5">
                        <Money amount={report.settlements?.finalized_net_total} emphasis />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Settlement lines</dt>
                      <dd className="mt-0.5 tabular-nums">{report.settlements?.total_lines ?? 0}</dd>
                    </div>
                  </dl>
                </div>

                <div className="border-t border-border pt-4">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Payments
                  </p>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      { label: "Completed", value: payments.completed_count },
                      { label: "Processing", value: payments.processing_count },
                      { label: "Pending", value: payments.pending_count },
                      { label: "Failed", value: payments.failed_count },
                    ].map((cell) => (
                      <div key={cell.label}>
                        <p className="text-xs text-muted-foreground">{cell.label}</p>
                        <p className="text-lg font-semibold tabular-nums">{cell.value ?? 0}</p>
                      </div>
                    ))}
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt className="text-muted-foreground">Paid</dt>
                      <dd className="mt-0.5">
                        <Money amount={payments.completed_amount} emphasis />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Outstanding</dt>
                      <dd className="mt-0.5">
                        <Money amount={payments.outstanding_amount} />
                      </dd>
                    </div>
                  </dl>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quantity by rate</CardTitle>
            <CardDescription>
              What was bought at each unit price the rate card resolved to.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {dashboard.state === "loading" ? (
              <LoadingState label="Loading rates…" />
            ) : !report ? (
              <p className="text-sm text-muted-foreground">Unavailable.</p>
            ) : (
              <BarBreakdown
                emptyTitle="No priced collection in this period"
                emptyDescription="Rate bands appear once milk has been collected and priced."
                rows={(report.rate_bands ?? []).map((band) => ({
                  key: String(band.unit_price),
                  label: `${band.unit_price} ${band.currency ?? ""} / kg`,
                  magnitude: band.total_net_weight_kg,
                  detail: (
                    <span className="flex items-center gap-2">
                      <Quantity value={band.total_net_weight_kg} unit="kg" />
                      <Money amount={band.payable_amount} currency={band.currency} />
                    </span>
                  ),
                }))}
              />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Centre performance</CardTitle>
            <CardDescription>Highest volume first, over the selected range.</CardDescription>
          </CardHeader>
          <CardContent>
            {centers.state === "loading" ? (
              <TableSkeleton rows={4} columns={3} />
            ) : centers.state === "forbidden" ? (
              <EmptyState
                title="Not part of your access"
                description="Your role does not include reporting. Nothing here is broken."
              />
            ) : centers.state === "error" ? (
              <ErrorState message={`Centre performance is unavailable — ${centers.message}.`} />
            ) : (
              <BarBreakdown
                emptyTitle="No centre activity in this period"
                rows={(centers.data.items ?? []).map((row) => ({
                  key: row.center_id,
                  label: row.center_name,
                  href: `/centers/${row.center_id}`,
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
            <CardTitle className="text-base">Top suppliers</CardTitle>
            <CardDescription>By quantity delivered over the selected range.</CardDescription>
          </CardHeader>
          <CardContent>
            {suppliers.state === "loading" ? (
              <TableSkeleton rows={4} columns={3} />
            ) : suppliers.state === "forbidden" ? (
              <EmptyState
                title="Not part of your access"
                description="Your role does not include reporting. Nothing here is broken."
              />
            ) : suppliers.state === "error" ? (
              <ErrorState message={`Supplier performance is unavailable — ${suppliers.message}.`} />
            ) : (
              <BarBreakdown
                emptyTitle="No supplier deliveries in this period"
                rows={(suppliers.data.items ?? []).map((row) => ({
                  key: row.supplier_id,
                  label: row.supplier_name,
                  href: `/suppliers/${row.supplier_id}`,
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
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent activity</CardTitle>
          <CardDescription>From the platform&apos;s own audit trail.</CardDescription>
        </CardHeader>
        <CardContent>
          {activity.state === "loading" ? (
            <TableSkeleton rows={5} columns={3} />
          ) : activity.state === "forbidden" ? (
            <EmptyState
              title="Not part of your access"
              description="Your role does not include reporting. Nothing here is broken."
            />
          ) : activity.state === "error" ? (
            <ErrorState message={`Recent activity is unavailable — ${activity.message}.`} />
          ) : (activity.data ?? []).length === 0 ? (
            <EmptyState title="No recorded activity yet" />
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {(activity.data ?? []).map((record) => (
                <li
                  key={record.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm"
                >
                  <span className="font-medium">{record.action.replace(/\./g, " ")}</span>
                  <span className="text-muted-foreground">{record.resource_type}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {String(record.created_at).slice(0, 19).replace("T", " ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
