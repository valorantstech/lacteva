"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FileText, Lock, Receipt as ReceiptIcon, Wallet } from "lucide-react";
import {
  ApiError,
  type CustomerPayment,
  type CustomerReceipt,
  type Invoice,
  type InvoicePageResult,
  listCustomerPayments,
  listCustomerReceipts,
  listCustomers,
  listInvoices,
  describeError,
} from "@/lib/api";
import { EntityPicker } from "@/components/entity-picker";
import { useCustomerNames } from "@/lib/names";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";
import { StatusBadge } from "@/components/status-badge";

/**
 * Billing (DEMO-009) — every customer's bills, payments and receipts.
 *
 * The customer detail page is where a bill is raised for one household; this
 * is the finance office's view across all of them. Filters are query
 * parameters, and a bill is only ever opened, never edited here.
 */

const PAGE_SIZE = 15;
const STATUSES = ["", "draft", "issued", "paid", "cancelled"] as const;

const describe = (e: unknown) => {
  if (e instanceof ApiError)
    return describeError(e);
  return e instanceof Error ? e.message : "Could not load billing";
};

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "—";

/**
 * DEMO-010: the page reads its filters from the URL, so the dashboard's
 * "three bills drafted and not yet issued → review" arrives at exactly those
 * three. It did not, and the link landed on the unfiltered list — which reads
 * as a filter that does not work, in front of a customer.
 */
export default function BillingPage() {
  return (
    <Suspense fallback={<div className="p-8" />}>
      <BillingView />
    </Suspense>
  );
}

function BillingView() {
  const searchParams = useSearchParams();
  const [page, setPage] = useState<InvoicePageResult | null>(null);
  const [customerFilterLabel, setCustomerFilterLabel] = useState("");
  const [payments, setPayments] = useState<CustomerPayment[]>([]);
  const [receipts, setReceipts] = useState<CustomerReceipt[]>([]);

  const [q, setQ] = useState(() => searchParams.get("q") ?? "");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>(
    () => (searchParams.get("status") as (typeof STATUSES)[number]) ?? "",
  );
  const [customerId, setCustomerId] = useState(
    () => searchParams.get("customer_id") ?? "",
  );
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filtered = Boolean(q || status || customerId);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listInvoices({
          q: q || undefined,
          status: status || undefined,
          customer_id: customerId || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
      listCustomerPayments({
        customer_id: customerId || undefined,
        limit: 8,
        offset: 0,
      })
        .then((p) => setPayments(p.items ?? []))
        .catch(() => setPayments([]));
      listCustomerReceipts({
        customer_id: customerId || undefined,
        limit: 8,
        offset: 0,
      })
        .then((p) => setReceipts(p.items ?? []))
        .catch(() => setReceipts([]));
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [customerId, offset, q, status]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 150);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {}, []);

  // P1-PORTAL-SCALE-001: resolve exactly the ids on screen (bills + payments).
  const names = useCustomerNames([
    ...(page?.items ?? []).map((i) => i.customer_id),
    ...payments.map((p) => p.customer_id),
  ]);

  const columns: Column<Invoice>[] = [
    {
      key: "number",
      header: "Bill",
      cell: (inv) => (
        <div className="flex flex-col">
          <Link
            className="font-medium hover:underline"
            href={`/invoices/${inv.id}`}
          >
            {inv.invoice_number}
          </Link>
          <span className="text-xs text-muted-foreground">
            {inv.line_count} {inv.line_count === 1 ? "delivery" : "deliveries"}
          </span>
        </div>
      ),
    },
    {
      key: "customer",
      header: "Customer",
      cell: (inv) => (
        <Link
          className="hover:underline"
          href={`/customers/${inv.customer_id}`}
        >
          {names[inv.customer_id] ?? `${inv.customer_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    {
      key: "period",
      header: "Period",
      secondary: true,
      cell: (inv) => (
        <span className="tabular-nums text-sm">
          {inv.period_from} → {inv.period_to}
        </span>
      ),
    },
    {
      key: "due",
      header: "Amount due",
      align: "end",
      cell: (inv) => (
        <div className="flex flex-col items-end">
          <Money amount={inv.amount_due} currency={inv.currency} />
          {Number(inv.previous_balance) !== 0 ? (
            <span className="text-xs text-muted-foreground">
              includes brought forward
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (inv) => (
        <span className="inline-flex items-center gap-1.5">
          <StatusBadge status={inv.status} />
          {inv.status === "issued" || inv.status === "paid" ? (
            <Lock
              aria-label="immutable"
              className="size-3 text-muted-foreground"
            />
          ) : null}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (inv) => (
        <Link
          href={`/invoices/${inv.id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          Open
        </Link>
      ),
    },
  ];

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Billing"
        description="Monthly bills, the money customers have paid, and the receipts they were given."
      />

      <section
        aria-label="Billing summary"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      >
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Bills"
            value={page ? page.total : "—"}
            caption={filtered ? "matching these filters" : "all periods"}
          />
          <span aria-hidden className="text-muted-foreground">
            <FileText className="size-4" />
          </span>
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Recent payments"
            value={payments.length}
            caption="most recent first"
          />
          <span aria-hidden className="text-muted-foreground">
            <Wallet className="size-4" />
          </span>
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Receipts issued"
            value={receipts.length}
            caption="generated by the platform"
          />
          <span aria-hidden className="text-muted-foreground">
            <ReceiptIcon className="size-4" />
          </span>
        </Surface>
      </section>

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Customer bills in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(inv) => inv.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered
                ? "No bill matches these filters"
                : "No bills yet",
              description: filtered
                ? "Try a different status, or clear the filters."
                : "Raise a customer's monthly bill from their page.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="bl-q">Search</Label>
                  <Input
                    id="bl-q"
                    className="h-9 w-48"
                    placeholder="Bill number"
                    value={q}
                    onChange={(e) => {
                      setQ(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <EntityPicker
                  id="bl-customer"
                  label="Customer"
                  placeholder="All customers — search to filter"
                  value={customerId}
                  valueLabel={customerFilterLabel || undefined}
                  onSelect={(id, label) => {
                    setCustomerId(id);
                    setCustomerFilterLabel(label);
                    setOffset(0);
                  }}
                  search={async (q, off) => {
                    const p = await listCustomers({
                      q: q || undefined,
                      limit: 20,
                      offset: off,
                    });
                    return {
                      items: (p.items ?? []).map((x) => ({
                        id: x.id,
                        label: x.name,
                        detail: x.code,
                      })),
                      total: p.total,
                    };
                  }}
                />
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="bl-status">Status</Label>
                  <Select
                    id="bl-status"
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
                  </Select>
                </div>
                {filtered ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setQ("");
                      setStatus("");
                      setCustomerId("");
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

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Payments received</CardTitle>
            <CardDescription>
              Money from customers to the dairy.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {payments.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No payments recorded yet.
              </p>
            ) : (
              <ul className="flex flex-col divide-y">
                {payments.map((pay) => (
                  <li
                    key={pay.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="flex flex-col">
                      <Link
                        className="text-sm font-medium hover:underline"
                        href={`/customers/${pay.customer_id}`}
                      >
                        {pay.payment_number}
                      </Link>
                      <span className="text-xs text-muted-foreground">
                        {names[pay.customer_id] ?? ""} · {pay.method} ·{" "}
                        {stamp(pay.received_at)}
                      </span>
                    </div>
                    <Money amount={pay.amount} currency={pay.currency} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Receipts</CardTitle>
            <CardDescription>
              Generated by the platform from each payment, and never changed.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {receipts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No receipts issued yet.
              </p>
            ) : (
              <ul className="flex flex-col divide-y">
                {receipts.map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {r.receipt_number}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {r.customer_name} · {r.payment_number} ·{" "}
                        {stamp(r.generated_at)}
                      </span>
                    </div>
                    <Money amount={r.amount} currency={r.currency} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
