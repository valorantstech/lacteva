"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Banknote, Droplets, Percent, Phone } from "lucide-react";
import {
  ApiError,
  type CollectionTrend,
  type DailyCollectionSummary,
  type MilkTransactionPage,
  type PaymentReport,
  type SettlementReport,
  type SupplierDetail,
  getCollectionTrend,
  getDailyReport,
  getPaymentReport,
  getSettlementReport,
  getSupplierDetail,
  listMilkTransactions,
  setSupplierStatus,
  describeError,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type DateRange,
  DateRangePicker,
  useDefaultRange,
} from "@/components/date-range";
import { TrendChart } from "@/components/trend-chart";
import { CurrencyTotals, Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  TableSkeleton,
} from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { useLocale } from "@/lib/i18n";

/**
 * One supplier (DEMO-003).
 *
 * Statistics, trend, settlements and payments are the platform's existing
 * aggregates filtered by `supplier_id` — all four contracts already accepted
 * that filter, so no endpoint was invented to fill this page.
 *
 * Activation lives here too, and it obeys the rule rather than working around
 * it: a supplier must be assigned to a collection centre before they can be
 * activated. The button asks the platform, and when the platform refuses, its
 * reason is shown verbatim.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;
const describe = (e: unknown) =>
  describeError(e, e instanceof Error
      ? e.message
      : "the request failed");

export default function SupplierDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const { currency: orgCurrency } = useLocale();
  const { id } = use(params);
  // Derived until the reader chooses, so a timezone that arrives after the
  // first render still corrects the window (DEMO-019).
  const [range, setRange] = useDefaultRange("30d");

  const [detail, setDetail] = useState<Load<SupplierDetail>>(LOADING);
  const [summary, setSummary] = useState<Load<DailyCollectionSummary>>(LOADING);
  const [trend, setTrend] = useState<Load<CollectionTrend>>(LOADING);
  const [recent, setRecent] = useState<Load<MilkTransactionPage>>(LOADING);
  const [settlements, setSettlements] =
    useState<Load<SettlementReport>>(LOADING);
  const [payments, setPayments] = useState<Load<PaymentReport>>(LOADING);
  const [metric, setMetric] = useState<"quantity" | "value">("quantity");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (window: DateRange) => {
      const params = {
        date_from: window.from,
        date_to: window.to,
        supplier_id: id,
      };
      const ok =
        <T,>(set: (v: Load<T>) => void) =>
        (data: T) =>
          set({ state: "ready", data });
      const fail =
        <T,>(set: (v: Load<T>) => void) =>
        (e: unknown) =>
          set({ state: "error", message: describe(e) });

      await Promise.allSettled([
        getSupplierDetail(id).then(ok(setDetail), fail(setDetail)),
        getDailyReport(params).then(ok(setSummary), fail(setSummary)),
        getCollectionTrend(params).then(ok(setTrend), fail(setTrend)),
        listMilkTransactions({ supplier_id: id, limit: 8, offset: 0 }).then(
          ok(setRecent),
          fail(setRecent),
        ),
        getSettlementReport({ supplier_id: id }).then(
          ok(setSettlements),
          fail(setSettlements),
        ),
        getPaymentReport({ supplier_id: id }).then(
          ok(setPayments),
          fail(setPayments),
        ),
      ]);
    },
    [id],
  );

  useEffect(() => {
    const t = setTimeout(() => void load(range), 0);
    return () => clearTimeout(t);
  }, [load, range]);

  const supplier = detail.state === "ready" ? detail.data.supplier : null;
  const centerIds =
    detail.state === "ready" ? (detail.data.center_ids ?? []) : [];
  const stats = summary.state === "ready" ? summary.data : null;
  const currencies = Object.entries(stats?.payable_by_currency ?? {});
  const primary = currencies[0];

  const changeStatus = async (next: string) => {
    setBusy(true);
    setNotice(null);
    try {
      await setSupplierStatus(id, next);
      setNotice(`Supplier is now ${next}.`);
      await load(range);
    } catch (err) {
      // The platform knows the rule; this repeats what it said.
      setNotice(
        err instanceof ApiError
          ? `Could not change status — ${err.detail}`
          : "Could not change status.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (detail.state === "error") {
    return (
      <PageContainer width="narrow">
        <ErrorState
          message={`This supplier could not be loaded — ${detail.message}.`}
        />
        <p className="mt-4 text-sm">
          <Link className="underline underline-offset-4" href="/suppliers">
            Back to suppliers
          </Link>
        </p>
      </PageContainer>
    );
  }

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[
          { label: "Suppliers", href: "/suppliers" },
          { label: supplier?.full_name ?? "Supplier" },
        ]}
        title={supplier?.full_name ?? "Supplier"}
        description={
          supplier ? `${supplier.code}` : "Loading this supplier's details…"
        }
        actions={
          supplier ? (
            <div className="flex items-center gap-2">
              <StatusBadge status={supplier.status} />
              {supplier.status === "draft" ||
              supplier.status === "suspended" ? (
                <Button
                  type="button"
                  size="sm"
                  disabled={busy}
                  onClick={() => void changeStatus("active")}
                >
                  Activate
                </Button>
              ) : null}
              {supplier.status === "active" ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void changeStatus("suspended")}
                >
                  Suspend
                </Button>
              ) : null}
            </div>
          ) : undefined
        }
      />

      {notice ? (
        <div
          role="status"
          className="rounded-md border border-border bg-card px-4 py-2 text-sm"
        >
          {notice}
        </div>
      ) : null}

      {supplier && supplier.status === "draft" && centerIds.length === 0 ? (
        <div
          role="note"
          className="rounded-md border border-border bg-muted/40 px-4 py-3 text-sm"
        >
          This supplier is not assigned to a collection centre yet. The platform
          will refuse to activate them until they are — a supplier needs
          somewhere to deliver.
        </div>
      ) : null}

      <DateRangePicker value={range} onChange={setRange} />

      {/*
        The four figures this page exists to show, on the metric scale. The
        VALUES are unchanged: <Money> and <Quantity> still render the
        platform's exact decimal strings — only their size and surface moved.
      */}
      <section
        aria-label="Supplier statistics"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <Surface tone="metric">
          <Metric
            label="Collections"
            value={stats ? String(stats.transactions) : "—"}
            caption={
              stats ? `${stats.accepted} accepted · ${stats.rejected} rejected` : undefined
            }
          />
        </Surface>
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric
            label="Quantity"
            value={stats ? <Quantity value={stats.total_net_weight_kg} unit={stats.quantity_unit} /> : "—"}
          />
          <Droplets aria-hidden className="size-4 text-muted-foreground" />
        </Surface>
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric
            label="Collection value"
            value={
              primary ? (
                <Money amount={primary[1]} currency={primary[0]} />
              ) : stats ? (
                <Money amount="0.00" currency={orgCurrency} />
              ) : (
                "—"
              )
            }
          />
          <Banknote aria-hidden className="size-4 text-muted-foreground" />
        </Surface>
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric
            label="Average fat"
            value={stats?.weighted_avg_fat != null ? `${stats.weighted_avg_fat}%` : "—"}
            caption="weighted by quantity"
          />
          <Percent aria-hidden className="size-4 text-muted-foreground" />
        </Surface>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Profile</CardTitle>
          </CardHeader>
          <CardContent>
            {detail.state === "loading" ? (
              <LoadingState label="Loading profile…" />
            ) : (
              <dl className="flex flex-col gap-2.5 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Code</dt>
                  <dd className="font-mono text-xs">{supplier?.code}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="flex items-center gap-1.5 text-muted-foreground">
                    <Phone aria-hidden className="size-3.5" />
                    Phone
                  </dt>
                  <dd>
                    {detail.data.profile?.phone || supplier?.phone || "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Village</dt>
                  <dd>{detail.data.profile?.village || "—"}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Assigned centres</dt>
                  <dd className="text-end">
                    {centerIds.length === 0 ? (
                      <span className="text-muted-foreground">none</span>
                    ) : (
                      <span className="flex flex-col items-end gap-1">
                        {centerIds.map((cid) => (
                          <Link
                            key={cid}
                            href={`/centers/${cid}`}
                            className="text-xs underline-offset-4 hover:underline"
                          >
                            {cid.slice(0, 8)}…
                          </Link>
                        ))}
                      </span>
                    )}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Bank accounts</dt>
                  <dd>{(detail.data.bank_accounts ?? []).length}</dd>
                </div>
              </dl>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Deliveries</CardTitle>
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
              <LoadingState label="Loading deliveries…" />
            ) : trend.state === "error" ? (
              <ErrorState message={`Unavailable — ${trend.message}.`} />
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
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Settlements</CardTitle>
            <CardDescription>Raised for this supplier.</CardDescription>
          </CardHeader>
          <CardContent>
            {settlements.state === "loading" ? (
              <LoadingState label="Loading settlements…" />
            ) : settlements.state === "error" ? (
              <ErrorState message={`Unavailable — ${settlements.message}.`} />
            ) : (settlements.data.by_status ?? []).length === 0 ? (
              <EmptyState title="No settlements yet" />
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  {(settlements.data.by_status ?? []).map((row) => (
                    <span
                      key={row.status}
                      className="flex items-center gap-1.5"
                    >
                      <StatusBadge status={row.status} />
                      <span className="text-sm tabular-nums text-muted-foreground">
                        {row.count}
                      </span>
                    </span>
                  ))}
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">
                      Finalized net total
                    </dt>
                    <dd className="mt-0.5">
                      <CurrencyTotals
                        totals={settlements.data.finalized_by_currency}
                        emphasis
                      />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Settlement lines</dt>
                    <dd className="mt-0.5 tabular-nums">
                      {settlements.data.total_lines ?? 0}
                    </dd>
                  </div>
                </dl>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Payments</CardTitle>
            <CardDescription>What this supplier has been paid.</CardDescription>
          </CardHeader>
          <CardContent>
            {payments.state === "loading" ? (
              <LoadingState label="Loading payments…" />
            ) : payments.state === "error" ? (
              <ErrorState message={`Unavailable — ${payments.message}.`} />
            ) : (payments.data.total_payments ?? 0) === 0 ? (
              <EmptyState title="No payments yet" />
            ) : (
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    {
                      label: "Completed",
                      value: payments.data.completed_count,
                    },
                    {
                      label: "Processing",
                      value: payments.data.processing_count,
                    },
                    { label: "Pending", value: payments.data.pending_count },
                    { label: "Failed", value: payments.data.failed_count },
                  ].map((cell) => (
                    <div key={cell.label}>
                      <p className="text-xs text-muted-foreground">
                        {cell.label}
                      </p>
                      <p className="text-lg font-semibold tabular-nums">
                        {cell.value ?? 0}
                      </p>
                    </div>
                  ))}
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Paid</dt>
                    <dd className="mt-0.5">
                      <CurrencyTotals
                        totals={payments.data.completed_by_currency}
                        emphasis
                      />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Outstanding</dt>
                    <dd className="mt-0.5">
                      <CurrencyTotals totals={payments.data.outstanding_by_currency} />
                    </dd>
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
        </CardHeader>
        <CardContent>
          {recent.state === "loading" ? (
            <TableSkeleton rows={5} columns={4} />
          ) : recent.state === "error" ? (
            <ErrorState message={`Unavailable — ${recent.message}.`} />
          ) : (recent.data.items ?? []).length === 0 ? (
            <EmptyState
              title="No collections yet"
              description="Deliveries appear here once this supplier brings milk to a centre."
            />
          ) : (
            <div className="w-full overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">
                  Recent collections for this supplier
                </caption>
                <thead>
                  <tr className="border-b border-border text-start text-muted-foreground">
                    <th scope="col" className="py-2 font-medium">
                      State
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      Milk
                    </th>
                    <th scope="col" className="py-2 text-end font-medium">
                      Net
                    </th>
                    <th scope="col" className="py-2 text-end font-medium">
                      Rate
                    </th>
                    <th scope="col" className="py-2 text-end font-medium">
                      Amount
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(recent.data.items ?? []).map((tx) => (
                    <tr
                      key={tx.id}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="py-2">
                        <StatusBadge status={tx.state} />
                      </td>
                      <td className="py-2 text-muted-foreground">
                        {tx.milk_type ?? "—"}
                      </td>
                      <td className="py-2 text-end">
                        <Quantity value={tx.net_weight} unit={tx.weight_unit} />
                      </td>
                      <td className="py-2 text-end tabular-nums text-muted-foreground">
                        {tx.unit_price ?? "—"}
                      </td>
                      <td className="py-2 text-end">
                        <Money
                          amount={tx.gross_amount}
                          currency={tx.currency}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
