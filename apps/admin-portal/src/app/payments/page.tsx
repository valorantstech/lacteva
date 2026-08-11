"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Banknote, CheckCircle2, Clock, XCircle } from "lucide-react";
import {
  ApiError,
  type BalancePageResult,
  PAYMENT_METHODS,
  type Payment,
  type PaymentPageResult,
  type PaymentReport,
  type SettlementBalance,
  type Supplier,
  createPayment,
  getPaymentReport,
  listOutstandingBalances,
  listPayments,
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
 * Payments (DEMO-006).
 *
 * A payment is raised against FINALIZED settlements — never against a
 * collection, never against a draft. So the way to start one here is the
 * platform's own selector, `/v1/payments/balances`: finalized settlements with
 * what is still owed on each. The portal does not compute what is owed; it asks.
 *
 * Filters are query parameters, the KPI row is `/v1/reports/payments`, and no
 * amount on this page was produced by arithmetic in a browser.
 */

const PAGE_SIZE = 15;

/** The real payment lifecycle. */
const STATUSES = [
  "",
  "draft",
  "pending",
  "processing",
  "completed",
  "failed",
  "cancelled",
] as const;

const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Request failed";
};

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "—";

export default function PaymentsPage() {
  const [page, setPage] = useState<PaymentPageResult | null>(null);
  const [report, setReport] = useState<PaymentReport | null>(null);
  const [balances, setBalances] = useState<BalancePageResult | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const [q, setQ] = useState("");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("");
  const [method, setMethod] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payFor, setPayFor] = useState<SettlementBalance | null>(null);

  const filtered = Boolean(q || status || method || supplierId);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listPayments({
          q: q || undefined,
          status: status || undefined,
          method: method || undefined,
          supplier_id: supplierId || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
      getPaymentReport({})
        .then(setReport)
        .catch(() => setReport(null));
      listOutstandingBalances({ supplier_id: supplierId || undefined, limit: 50, offset: 0 })
        .then(setBalances)
        .catch(() => setBalances(null));
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [method, offset, q, status, supplierId]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 150);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    listSuppliers({ limit: 100, offset: 0 })
      .then((s) => setSuppliers(s.items ?? []))
      .catch(() => setSuppliers([]));
  }, []);

  const supplierName = useMemo(
    () => Object.fromEntries(suppliers.map((s) => [s.id, s.full_name])),
    [suppliers],
  );

  const columns: Column<Payment>[] = [
    {
      key: "number",
      header: "Payment",
      cell: (p) => (
        <div className="flex flex-col">
          <Link className="font-medium hover:underline" href={`/payments/${p.id}`}>
            {p.payment_number}
          </Link>
          <span className="text-xs text-muted-foreground">
            {stamp(p.created_at)} · {p.line_count}{" "}
            {p.line_count === 1 ? "settlement" : "settlements"}
          </span>
        </div>
      ),
    },
    {
      key: "supplier",
      header: "Supplier",
      cell: (p) => (
        <Link className="hover:underline" href={`/suppliers/${p.supplier_id}`}>
          {supplierName[p.supplier_id] ?? `${p.supplier_id.slice(0, 8)}…`}
        </Link>
      ),
    },
    { key: "method", header: "Method", secondary: true, cell: (p) => p.method },
    {
      key: "reference",
      header: "Reference",
      secondary: true,
      cell: (p) => <span className="font-mono text-xs">{p.reference || "—"}</span>,
    },
    {
      key: "amount",
      header: "Amount",
      align: "end",
      cell: (p) => <Money amount={p.amount} currency={p.currency} />,
    },
    {
      key: "status",
      header: "Status",
      cell: (p) => (
        <div className="flex flex-col gap-0.5">
          <StatusBadge status={p.status} />
          {p.status === "failed" && p.failure_reason ? (
            <span className="max-w-56 truncate text-xs text-destructive" title={p.failure_reason}>
              {p.failure_reason}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (p) => (
        <Link
          href={`/payments/${p.id}`}
          className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
        >
          Open
        </Link>
      ),
    },
  ];

  const owed = (balances?.items ?? []).filter((b) => !b.fully_paid);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Payments"
        description="Money paid against finalized settlements. This platform records movement; it does not perform it."
      />

      <section aria-label="Payment summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Completed"
          value={report ? report.completed_count : "—"}
          hint={
            report ? (
              <>
                <Money amount={report.completed_amount} currency="KES" /> paid
              </>
            ) : undefined
          }
          icon={<CheckCircle2 className="size-4" />}
        />
        <StatTile
          label="In flight"
          value={report ? report.pending_count + report.processing_count : "—"}
          hint={
            report ? `${report.pending_count} pending · ${report.processing_count} processing` : undefined
          }
          icon={<Clock className="size-4" />}
        />
        <StatTile
          label="Failed"
          value={report ? report.failed_count : "—"}
          hint={
            report ? (
              <>
                <Money amount={report.failed_amount} currency="KES" /> to retry
              </>
            ) : undefined
          }
          icon={<XCircle className="size-4" />}
        />
        <StatTile
          label="Outstanding"
          value={report ? <Money amount={report.outstanding_amount} currency="KES" /> : "—"}
          hint="finalized but unpaid"
          icon={<Banknote className="size-4" />}
        />
      </section>

      {/* --- Raise a payment ---------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Settlements awaiting payment</CardTitle>
          <CardDescription>
            Finalized settlements with money still owed, as the platform computes it. Allocated
            counts live payments including drafts, so a settlement can never be paid twice.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {owed.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing is outstanding — every finalized settlement is fully allocated.
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {owed.slice(0, 8).map((b) => (
                <li key={b.settlement_id} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex flex-col">
                    <Link
                      className="font-medium hover:underline"
                      href={`/settlements/${b.settlement_id}`}
                    >
                      {b.settlement_number}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {supplierName[b.supplier_id] ?? `${b.supplier_id.slice(0, 8)}…`} · payable{" "}
                      <Money amount={b.payable} currency={b.currency} />
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-medium">
                      <Money amount={b.outstanding} currency={b.currency} />
                    </span>
                    <Button type="button" size="sm" onClick={() => setPayFor(b)}>
                      Pay
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {owed.length > 8 ? (
            <p className="pt-3 text-xs text-muted-foreground">
              Showing 8 of {owed.length} outstanding settlements — filter by supplier to narrow.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {payFor ? (
        <CreatePaymentCard
          balance={payFor}
          onClose={() => setPayFor(null)}
          onCreated={() => {
            setPayFor(null);
            setOffset(0);
            void load();
          }}
        />
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Payments in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(p) => p.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title: filtered ? "No payment matches these filters" : "No payments yet",
              description: filtered
                ? "Try a different status or method, or clear the filters."
                : "Finalize a settlement, then pay it from the list above.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pm-q">Search</Label>
                  <Input
                    id="pm-q"
                    className="h-9 w-52"
                    placeholder="Number or reference"
                    value={q}
                    onChange={(e) => {
                      setQ(e.target.value);
                      setOffset(0);
                    }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pm-status">Status</Label>
                  <select
                    id="pm-status"
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
                  <Label htmlFor="pm-method">Method</Label>
                  <select
                    id="pm-method"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={method}
                    onChange={(e) => {
                      setMethod(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All methods</option>
                    {PAYMENT_METHODS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pm-supplier">Supplier</Label>
                  <select
                    id="pm-supplier"
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
                      setMethod("");
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
 * Raising a payment against one finalized settlement.
 *
 * The amount defaults to the platform's own `outstanding` and is sent as the
 * STRING it arrived as — the portal never rounds it, and never reconstructs it
 * from payable minus paid.
 */
function CreatePaymentCard({
  balance,
  onClose,
  onCreated,
}: {
  balance: SettlementBalance;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [method, setMethod] = useState<string>(PAYMENT_METHODS[0]);
  const [amount, setAmount] = useState(String(balance.outstanding));
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createPayment({
        supplier_id: balance.supplier_id,
        currency: balance.currency,
        method,
        allocations: [{ settlement_id: balance.settlement_id, amount }],
        reference: reference || undefined,
        note: note || undefined,
      });
      onCreated();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pay {balance.settlement_number}</CardTitle>
        <CardDescription>
          Outstanding <Money amount={balance.outstanding} currency={balance.currency} />. The payment
          is created as a draft — approving and executing it are separate, deliberate steps.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="np-method">Method</Label>
              <select
                id="np-method"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                {PAYMENT_METHODS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="np-amount">Amount ({balance.currency})</Label>
              <Input
                id="np-amount"
                required
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Defaults to the full outstanding balance. A smaller figure is a partial payment.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="np-reference">Reference</Label>
              <Input
                id="np-reference"
                placeholder="optional"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="np-note">Note</Label>
              <Input
                id="np-note"
                placeholder="optional"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>
          {error ? (
            <p role="alert" className="inline-flex items-start gap-2 text-sm text-destructive">
              <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
              The platform refused: {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create draft payment"}
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
