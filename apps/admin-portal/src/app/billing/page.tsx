"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  FileText,
  Lock,
  MessageCircle,
  Receipt as ReceiptIcon,
  Wallet,
} from "lucide-react";
import {
  ApiError,
  type CustomerPayment,
  type CustomerReceipt,
  type Invoice,
  type InvoicePageResult,
  type IssueBatchResult,
  type MeOrganization,
  getMe,
  issueInvoicesBatch,
  listCustomerPayments,
  listCustomerReceipts,
  listCustomers,
  listInvoices,
  describeError,
} from "@/lib/api";
import { EntityPicker } from "@/components/entity-picker";
import { useCustomerNames, useCustomerPhones } from "@/lib/names";
import { billSummary, waMeLink } from "@/lib/whatsapp";
import { useBusinessToday } from "@/components/date-range";
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
  // WO-83 §3: the phones the per-row WhatsApp links go to, same discipline.
  const phones = useCustomerPhones((page?.items ?? []).map((i) => i.customer_id));
  const [organization, setOrganization] = useState<MeOrganization | null>(null);
  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) setOrganization(me.organization ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

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
        <span className="inline-flex items-center gap-1">
          <RowWhatsApp
            invoice={inv}
            phone={phones[inv.customer_id]}
            organization={organization}
          />
          <Link
            href={`/invoices/${inv.id}`}
            className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
          >
            Open
          </Link>
        </span>
      ),
    },
  ];

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Billing"
        description="Monthly bills, the money customers have paid, and the receipts they were given."
        actions={<IssueAll onIssued={() => void load()} />}
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


/**
 * The per-row "Send on WhatsApp" (WO-83 §3): a `wa.me` link with the summary
 * typed, disabled with the reason when the customer has no phone. The portal
 * never sends; the operator presses send in WhatsApp.
 */
function RowWhatsApp({
  invoice,
  phone,
  organization,
}: {
  invoice: Invoice;
  phone: string | undefined;
  organization: MeOrganization | null;
}) {
  const href = phone
    ? waMeLink(
        phone,
        billSummary({
          organization: organization?.name ?? "",
          invoice_number: invoice.invoice_number,
          period_from: invoice.period_from,
          period_to: invoice.period_to,
          currency: invoice.currency,
          total: invoice.total,
          previous_balance: invoice.previous_balance,
          amount_due: invoice.amount_due,
          pay_to: organization?.pay_to ?? null,
        }),
      )
    : null;
  if (!href)
    return (
      <span
        className="inline-flex h-8 items-center rounded-md border border-input px-2 text-xs text-muted-foreground opacity-60"
        title="No phone on this customer"
        aria-disabled="true"
        data-testid={`whatsapp-none-${invoice.invoice_number}`}
      >
        <MessageCircle aria-hidden className="size-3.5" />
        <span className="sr-only">Send on WhatsApp — no phone on this customer</span>
      </span>
    );
  return (
    <a
      className="inline-flex h-8 items-center rounded-md border border-input px-2 text-sm hover:bg-muted"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title="Send on WhatsApp"
      data-testid={`whatsapp-${invoice.invoice_number}`}
    >
      <MessageCircle aria-hidden className="size-4" />
      <span className="sr-only">Send on WhatsApp</span>
    </a>
  );
}

/** The first and last day of the calendar month before `today` (YYYY-MM-DD). */
function previousMonth(today: string): { from: string; to: string } {
  const [y, m] = today.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 2, 1));
  const last = new Date(Date.UTC(y, m - 1, 0));
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { from: iso(first), to: iso(last) };
}

/**
 * "Issue all" (WO-83 §1). The platform is asked first for a PREVIEW — how
 * many drafts the period holds and what they come to — and that is what the
 * confirm shows. Only a second, explicit press issues them, in one act, and
 * the exceptions the platform declined are listed afterwards by number and
 * reason. Nothing is summed here; the count and the total are the platform's.
 */
function IssueAll({ onIssued }: { onIssued: () => void }) {
  const today = useBusinessToday();
  const defaults = previousMonth(today);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(defaults.from);
  const [to, setTo] = useState(defaults.to);
  const [preview, setPreview] = useState<IssueBatchResult | null>(null);
  const [result, setResult] = useState<IssueBatchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function lookAhead() {
    setBusy(true);
    setFailure(null);
    setResult(null);
    try {
      setPreview(
        await issueInvoicesBatch({ period_from: from, period_to: to, preview: true }),
      );
    } catch (err) {
      setFailure(describe(err));
    } finally {
      setBusy(false);
    }
  }

  async function issue() {
    setBusy(true);
    setFailure(null);
    try {
      const done = await issueInvoicesBatch({ period_from: from, period_to: to });
      setResult(done);
      setPreview(null);
      onIssued();
    } catch (err) {
      setFailure(describe(err));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <Button type="button" size="sm" onClick={() => setOpen(true)}>
        Issue all drafts…
      </Button>
    );

  return (
    <div
      className="flex w-full max-w-md flex-col gap-3 rounded-md border border-border bg-card p-3 text-sm"
      role="group"
      aria-label="Issue every draft bill for a period"
    >
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="issue-all-from">Period from</Label>
          <Input
            id="issue-all-from"
            type="date"
            value={from}
            disabled={busy}
            onChange={(e) => {
              setFrom(e.target.value);
              setPreview(null);
            }}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="issue-all-to">Period to</Label>
          <Input
            id="issue-all-to"
            type="date"
            value={to}
            disabled={busy}
            onChange={(e) => {
              setTo(e.target.value);
              setPreview(null);
            }}
          />
        </div>
      </div>
      {failure ? (
        <p role="alert" className="text-destructive">
          The platform refused: {failure}
        </p>
      ) : null}
      {preview ? (
        <div className="flex flex-col gap-2" data-testid="issue-all-confirm">
          <p>
            <strong>{preview.issued.length}</strong> draft
            {preview.issued.length === 1 ? "" : "s"} will be issued, coming to{" "}
            <strong>
              <Money amount={preview.total} currency={preview.currency ?? ""} />
            </strong>
            . An issued bill cannot be edited; corrections become adjustments.
          </p>
          {preview.skipped.length > 0 ? (
            <p className="text-muted-foreground">
              {preview.skipped.length} will be left alone:{" "}
              {preview.skipped.map((s) => `${s.invoice_number} (${s.reason})`).join(", ")}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={busy || preview.issued.length === 0}
              onClick={() => void issue()}
            >
              Issue all {preview.issued.length}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => setPreview(null)}
            >
              Not now
            </Button>
          </div>
        </div>
      ) : result ? (
        <div className="flex flex-col gap-1" role="status" data-testid="issue-all-result">
          <p>
            Issued <strong>{result.issued.length}</strong>, coming to{" "}
            <Money amount={result.total} currency={result.currency ?? ""} />.
          </p>
          {result.skipped.length > 0 ? (
            <ul className="list-disc pl-5 text-muted-foreground">
              {result.skipped.map((s) => (
                <li key={s.invoice_id}>
                  {s.invoice_number}: {s.reason}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">No exceptions.</p>
          )}
          <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Done
          </Button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button type="button" size="sm" disabled={busy} onClick={() => void lookAhead()}>
            {busy ? "Counting…" : "Count the drafts"}
          </Button>
          <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
