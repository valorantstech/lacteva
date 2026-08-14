"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Banknote,
  CalendarClock,
  CalendarPlus,
  Download,
  Droplets,
  Truck,
  Users,
} from "lucide-react";
import {
  ApiError,
  type Customer,
  type Delivery,
  type DeliveryPageResult,
  type DeliveryReport,
  deliveryReportCsvUrl,
  generateDeliveries,
  type GenerationResult,
  type GenerationRun,
  listGenerationRuns,
  getDeliveryReport,
  listCustomers,
  listDeliveries,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import {
  type DateRange,
  DateRangePicker,
  resolveRange,
} from "@/components/date-range";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useLocale } from "@/lib/i18n";

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
  if (e instanceof ApiError)
    return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
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
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const { currency: orgCurrency, timezone: orgTimezone, t } = useLocale();

  const searchParams = useSearchParams();
  const [page, setPage] = useState<DeliveryPageResult | null>(null);
  const [report, setReport] = useState<DeliveryReport | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);

  const [range, setRange] = useState<DateRange>(() =>
    resolveRange("7d", orgTimezone),
  );
  const [customerId, setCustomerId] = useState(
    () => searchParams.get("customer_id") ?? "",
  );
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
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<GenerationResult | null>(null);
  const [lastRun, setLastRun] = useState<GenerationRun | null>(null);

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
      // DEMO-017 §10. Context, never a blocker: a scheduler whose history
      // cannot be read must not stop a manager reading the round itself.
      listGenerationRuns(1)
        .then((runs) => setLastRun(runs[0] ?? null))
        .catch(() => setLastRun(null));
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
    {
      key: "product",
      header: "Product",
      secondary: true,
      cell: (d) => d.product,
    },
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
    {
      key: "status",
      header: "Status",
      cell: (d) => <StatusBadge status={d.status} />,
    },
    {
      key: "billed",
      header: "Billed",
      secondary: true,
      cell: (d) =>
        d.invoice_id ? (
          <Link
            className="text-sm hover:underline"
            href={`/invoices/${d.invoice_id}`}
          >
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
        title={t("delivery.title")}
        description={t("delivery.subtitle")}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <DateRangePicker value={range} onChange={setRange} busy={loading} />
        {/*
          A plain link, not a fetch-and-blob. The proxy streams the file with
          its Content-Disposition intact, so the browser saves it the way it
          saves any download — and nothing about the report is assembled in
          JavaScript, which is the point of §15.
        */}
        <div className="flex flex-wrap items-center gap-3">
          {/*
          DEMO-016. Running this twice is safe — idempotency is a database
          constraint, not a check in the browser — so the button is not
          disabled after a run and the result says how many already existed.
        */}
          <Button
            type="button"
            variant="secondary"
            disabled={generating}
            onClick={async () => {
              setGenerating(true);
              setGenerated(null);
              try {
                setGenerated(await generateDeliveries({ for_date: range.to }));
                await load();
              } catch (err) {
                setError(
                  err instanceof ApiError ? err.detail : t("generation.failed"),
                );
              } finally {
                setGenerating(false);
              }
            }}
          >
            <CalendarPlus className="size-4" />
            {t("generation.run")}
          </Button>
          <a
            href={deliveryReportCsvUrl({
              date_from: range.from,
              date_to: range.to,
              customer_id: customerId || undefined,
              status: status || undefined,
            })}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-accent"
          >
            <Download className="size-4" />
            {t("delivery.downloadCsv")}
          </a>
        </div>
      </div>

      {/*
        DEMO-017 §10: one line, not a dashboard. It answers the question an
        operator actually has at 06:00 — did the round go out, and if not, is
        it safe for me to press the button? The answer to the second is always
        yes, and the notice says so when the last run failed.
      */}
      {lastRun ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span>
            {t("generation.lastRun")}:{" "}
            <span className="text-foreground">{lastRun.business_date}</span>
          </span>
          <StatusBadge status={lastRun.status} />
          <span>
            {t(`generation.trigger.${lastRun.trigger}`)}
            {lastRun.attempts > 1
              ? ` · ${t("generation.attempt", { count: lastRun.attempts })}`
              : ""}
          </span>
          <span>
            {t("generation.created", { count: lastRun.created })}
            {lastRun.already_present > 0
              ? ` · ${t("generation.alreadyPresent", { count: lastRun.already_present })}`
              : ""}
          </span>
          {lastRun.status === "failed" ? (
            <span className="text-amber-700 dark:text-amber-500">
              {t("generation.failedNotice")}
            </span>
          ) : null}
        </div>
      ) : null}

      {generated ? (
        <div
          role="status"
          className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm"
        >
          {/*
            "Nothing due" and "nothing NEW" are different answers and a test
            caught them being conflated: a second run finds six due and creates
            none, which is idempotency working — not an empty day.
          */}
          {generated.created > 0
            ? t("generation.created", { count: generated.created })
            : generated.due > 0
              ? t("generation.created", { count: 0 })
              : t("generation.nothingDue")}
          {generated.already_present > 0
            ? ` · ${t("generation.alreadyPresent", { count: generated.already_present })}`
            : ""}
          <span className="ms-2 text-xs text-muted-foreground">
            {t("generation.idempotent")}
          </span>
        </div>
      ) : null}

      <section
        aria-label={t("delivery.summary")}
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <StatTile
          label={t("delivery.title")}
          value={report ? report.deliveries : "—"}
          hint={
            report
              ? t("delivery.skippedCount", { count: report.skipped })
              : undefined
          }
          icon={<Truck className="size-4" />}
        />
        {/* DEMO-019 §5: what the round intended, beside what it achieved.
            Only when they differ — a day that went to plan does not need a
            tile telling a manager it went to plan. */}
        {report &&
        report.planned_quantity !== undefined &&
        String(report.planned_quantity) !== String(report.total_quantity) ? (
          <StatTile
            label={t("delivery.plannedQuantity")}
            value={
              <Quantity
                value={report.planned_quantity}
                unit={report.quantity_unit}
              />
            }
            hint={
              report.returned
                ? `${t("delivery.returned")}: ${report.returned}`
                : undefined
            }
            icon={<Droplets className="size-4" />}
          />
        ) : null}
        <StatTile
          label={t("field.quantity")}
          value={
            report ? (
              <Quantity
                value={report.total_quantity}
                unit={report.quantity_unit}
              />
            ) : (
              "—"
            )
          }
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label={t("delivery.value")}
          value={
            report ? (
              <Money amount={report.total_amount} currency={report.currency} />
            ) : (
              "—"
            )
          }
          icon={<Banknote className="size-4" />}
        />
        <StatTile
          label={t("delivery.customersServed")}
          value={report ? report.customers_served : "—"}
          icon={<Users className="size-4" />}
        />
        {/* DEMO-016 §13: the operator's "how many are left?". Only shown when
            there is a generated round to be left of — a dairy that types its
            deliveries has no pending count and does not need a zero. */}
        {report && (report.scheduled ?? 0) > 0 ? (
          <StatTile
            label={t("delivery.pending")}
            value={report.scheduled ?? 0}
            hint={
              report.planned
                ? `${t("delivery.planned")}: ${report.planned}`
                : undefined
            }
            icon={<CalendarClock className="size-4" />}
          />
        ) : null}
      </section>

      {/*
        `?.` deliberately. During a rolling deploy the portal can be newer than
        the API for a few seconds — DEMO-013 spent an outage in exactly that
        state — and a screen that throws because a field it expected is absent
        turns a brief version skew into a blank page.
      */}
      {report && report.by_customer?.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {t("delivery.byCustomer")}
            </CardTitle>
            <CardDescription>{t("delivery.byCustomerHint")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">
                  {t("delivery.byCustomer")}
                </caption>
                <thead>
                  <tr className="border-b text-start text-muted-foreground">
                    <th className="py-2 pe-4 font-medium">
                      {t("nav.customers")}
                    </th>
                    <th className="py-2 pe-4 text-end font-medium">
                      {t("delivery.title")}
                    </th>
                    <th className="py-2 pe-4 text-end font-medium">
                      {t("field.quantity")}
                    </th>
                    <th className="py-2 pe-4 text-end font-medium">
                      {t("delivery.rate")}
                    </th>
                    <th className="py-2 text-end font-medium">
                      {t("field.amount")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.by_customer.map((row) => (
                    <tr
                      key={row.customer_id}
                      className="border-b last:border-0"
                    >
                      <td className="py-2 pe-4">
                        <Link
                          href={`/customers/${row.customer_id}`}
                          className="font-medium hover:underline"
                        >
                          {row.name}
                        </Link>
                        <span className="ms-2 text-xs text-muted-foreground">
                          {row.code}
                        </span>
                        {row.skipped > 0 ? (
                          <span className="ms-2 text-xs text-muted-foreground">
                            {row.skipped} {t("delivery.skipped").toLowerCase()}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 pe-4 text-end tabular-nums">
                        {row.deliveries}
                      </td>
                      <td className="py-2 pe-4 text-end">
                        <Quantity
                          value={row.quantity}
                          unit={report.quantity_unit}
                        />
                      </td>
                      <td className="py-2 pe-4 text-end">
                        {/* Null means the rate changed inside this window. The
                            platform declines to average two rates; so does the
                            screen. */}
                        {row.unit_price === null ? (
                          <span className="text-muted-foreground">
                            {t("delivery.mixedRate")}
                          </span>
                        ) : (
                          <Money
                            amount={row.unit_price}
                            currency={report.currency}
                          />
                        )}
                      </td>
                      <td className="py-2 text-end">
                        <Money amount={row.amount} currency={report.currency} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {report && report.by_day?.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Day by day</CardTitle>
            <CardDescription>
              Grouped by the database over {report.date_from} → {report.date_to}
              .
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Deliveries per day</caption>
                <thead>
                  <tr className="border-b text-start text-muted-foreground">
                    <th className="py-2 pe-4 font-medium">Date</th>
                    <th className="py-2 pe-4 text-end font-medium">
                      Deliveries
                    </th>
                    <th className="py-2 pe-4 text-end font-medium">
                      Customers
                    </th>
                    <th className="py-2 pe-4 text-end font-medium">Quantity</th>
                    <th className="py-2 text-end font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {report.by_day.map((day) => (
                    <tr
                      key={day.delivery_date}
                      className="border-b last:border-0"
                    >
                      <td className="py-2 pe-4 tabular-nums">
                        {day.delivery_date}
                      </td>
                      <td className="py-2 pe-4 text-end tabular-nums">
                        {day.deliveries}
                      </td>
                      <td className="py-2 pe-4 text-end tabular-nums">
                        {day.customers}
                      </td>
                      <td className="py-2 pe-4 text-end">
                        <Quantity
                          value={day.quantity}
                          unit={report.quantity_unit}
                        />
                      </td>
                      <td className="py-2 text-end">
                        <Money amount={day.amount} currency={report.currency} />
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
              title: filtered
                ? "No delivery matches these filters"
                : "No deliveries in this period",
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
              <span className="text-muted-foreground">
                Across all {page.total} matching deliveries:{" "}
              </span>
              <Quantity value={page.total_quantity} unit="L" />
              <span className="text-muted-foreground"> · </span>
              <Money amount={page.total_amount} currency={orgCurrency} />
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
