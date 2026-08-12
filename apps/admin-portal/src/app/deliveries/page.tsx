"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Banknote, Droplets, Truck, Users } from "lucide-react";
import {
  ApiError,
  type Customer,
  type Delivery,
  type DeliveryPageResult,
  type DeliveryReport,
  getDeliveryReport,
  listCustomers,
  listDeliveries,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { type DateRange, DateRangePicker, resolveRange } from "@/components/date-range";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

/**
 * Daily deliveries and the delivery report (DEMO-009).
 *
 * The report a dairy's customers asked for by name: "what milk was delivered
 * today?" and "what over this period?".
 *
 * Both answers are the platform's. The KPI row is
 * `/v1/deliveries/report`, which groups in SQL; the per-day breakdown is the
 * same aggregate's `by_day`; and the table's totals cover the WHOLE filtered
 * set rather than the visible page, because a report that adds up one page is
 * not a report. Nothing on this screen sums a column in the browser.
 */

const PAGE_SIZE = 25;
const STATUSES = ["", "delivered", "skipped", "returned", "cancelled"] as const;

const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Could not load deliveries";
};

/**
 * DEMO-010: the page reads its filters from the URL, so the dashboard's
 * "22 deliveries made but not yet billed → review" arrives showing exactly
 * those twenty-two. It did not, and the link landed on the unfiltered list.
 */
export default function DeliveriesPage() {
  return (
    <Suspense fallback={<div className="p-8" />}>
      <DeliveriesView />
    </Suspense>
  );
}

function DeliveriesView() {
  const searchParams = useSearchParams();
  const [page, setPage] = useState<DeliveryPageResult | null>(null);
  const [report, setReport] = useState<DeliveryReport | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);

  const [range, setRange] = useState<DateRange>(() => resolveRange("7d"));
  const [customerId, setCustomerId] = useState(() => searchParams.get("customer_id") ?? "");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>(
    () => (searchParams.get("status") as (typeof STATUSES)[number]) ?? "",
  );
  // "" = every delivery, "true" = already on a bill, "false" = not yet billed.
  // A tri-state because "unbilled" and "no opinion" are different questions.
  const [billed, setBilled] = useState<"" | "true" | "false">(() => {
    const raw = searchParams.get("invoiced");
    return raw === "true" || raw === "false" ? raw : "";
  });
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filtered = Boolean(customerId || status || billed);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listDeliveries({
          customer_id: customerId || undefined,
          date_from: range.from,
          date_to: range.to,
          status: status || undefined,
          invoiced: billed === "" ? undefined : billed === "true",
          limit: PAGE_SIZE,
          offset,
        }),
      );
      // The aggregate over the same window. A reporting hiccup must not blank
      // the table.
      getDeliveryReport({
        date_from: range.from,
        date_to: range.to,
        customer_id: customerId || undefined,
      })
        .then(setReport)
        .catch(() => setReport(null));
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [billed, customerId, offset, range.from, range.to, status]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    listCustomers({ limit: 100, offset: 0 })
      .then((c) => setCustomers(c.items ?? []))
      .catch(() => setCustomers([]));
  }, []);

  const names = useMemo(
    () => Object.fromEntries(customers.map((c) => [c.id, c.name])),
    [customers],
  );

  const columns: Column<Delivery>[] = [
    {
      key: "date",
      header: "Delivered",
      cell: (d) => (
        <div className="flex flex-col">
          <span className="font-medium tabular-nums">{d.delivery_date}</span>
          <span className="text-xs text-muted-foreground">{d.slot}</span>
        </div>
      ),
    },
    {
      key: "customer",
      header: "Customer",
      cell: (d) => (
        <Link className="hover:underline" href={`/customers/${d.customer_id}`}>
          {names[d.customer_id] ?? `${d.customer_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    { key: "product", header: "Product", secondary: true, cell: (d) => d.product },
    {
      key: "quantity",
      header: "Quantity",
      align: "end",
      cell: (d) => <Quantity value={d.quantity} unit={d.quantity_unit} />,
    },
    {
      key: "amount",
      header: "Amount",
      align: "end",
      cell: (d) => (
        <div className="flex flex-col items-end">
          <Money amount={d.amount} currency={d.currency} />
          <span className="text-xs tabular-nums text-muted-foreground">
            @ {String(d.unit_price)}
          </span>
        </div>
      ),
    },
    { key: "status", header: "Status", cell: (d) => <StatusBadge status={d.status} /> },
    {
      key: "billed",
      header: "Billed",
      secondary: true,
      cell: (d) =>
        d.invoice_id ? (
          <Link className="text-sm hover:underline" href={`/invoices/${d.invoice_id}`}>
            on a bill
          </Link>
        ) : (
          <span className="text-xs text-muted-foreground">not yet</span>
        ),
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Deliveries"
        description="Milk leaving for customers — what went out, to whom, and what it is worth."
      />

      <DateRangePicker value={range} onChange={setRange} busy={loading} />

      <section aria-label="Delivery summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Deliveries"
          value={report ? report.deliveries : "—"}
          hint={report ? `${report.skipped} skipped` : undefined}
          icon={<Truck className="size-4" />}
        />
        <StatTile
          label="Quantity"
          value={report ? <Quantity value={report.total_quantity} unit="L" /> : "—"}
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label="Value"
          value={report ? <Money amount={report.total_amount} currency="KES" /> : "—"}
          icon={<Banknote className="size-4" />}
        />
        <StatTile
          label="Customers served"
          value={report ? report.customers_served : "—"}
          icon={<Users className="size-4" />}
        />
      </section>

      {report && report.by_day.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Day by day</CardTitle>
            <CardDescription>
              Grouped by the database over {report.date_from} → {report.date_to}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Deliveries per day</caption>
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Date</th>
                    <th className="py-2 pr-4 text-right font-medium">Deliveries</th>
                    <th className="py-2 pr-4 text-right font-medium">Customers</th>
                    <th className="py-2 pr-4 text-right font-medium">Quantity</th>
                    <th className="py-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {report.by_day.map((day) => (
                    <tr key={day.delivery_date} className="border-b last:border-0">
                      <td className="py-2 pr-4 tabular-nums">{day.delivery_date}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{day.deliveries}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{day.customers}</td>
                      <td className="py-2 pr-4 text-right">
                        <Quantity value={day.quantity} unit="L" />
                      </td>
                      <td className="py-2 text-right">
                        <Money amount={day.amount} currency="KES" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Milk deliveries in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(d) => d.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered ? "No delivery matches these filters" : "No deliveries in this period",
              description: filtered
                ? "Try a wider date range, or clear the filters."
                : "Record a delivery from a customer's page.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="dl-customer">Customer</Label>
                  <select
                    id="dl-customer"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={customerId}
                    onChange={(e) => {
                      setCustomerId(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All customers</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="dl-status">Status</Label>
                  <select
                    id="dl-status"
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
                  <Label htmlFor="dl-billed">Billed</Label>
                  <select
                    id="dl-billed"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={billed}
                    onChange={(e) => {
                      setBilled(e.target.value as "" | "true" | "false");
                      setOffset(0);
                    }}
                  >
                    <option value="">Billed or not</option>
                    <option value="false">Not yet billed</option>
                    <option value="true">Already billed</option>
                  </select>
                </div>
                {filtered ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setCustomerId("");
                      setStatus("");
                      setBilled("");
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
          {page ? (
            <p className="pt-3 text-sm">
              <span className="text-muted-foreground">Across all {page.total} matching deliveries: </span>
              <Quantity value={page.total_quantity} unit="L" />
              <span className="text-muted-foreground"> · </span>
              <Money amount={page.total_amount} currency="KES" />
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
