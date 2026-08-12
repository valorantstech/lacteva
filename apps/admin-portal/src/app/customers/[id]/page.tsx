"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Receipt as ReceiptIcon, Truck, Wallet } from "lucide-react";
import {
  ApiError,
  CUSTOMER_PAYMENT_METHODS,
  type CustomerBalance,
  type CustomerDetail,
  type CustomerPayment,
  type CustomerReceipt,
  type Delivery,
  type DeliveryPageResult,
  type Invoice,
  generateInvoice,
  getCustomer,
  getCustomerBalance,
  listCustomerPayments,
  listCustomerReceipts,
  listDeliveries,
  listInvoices,
  recordCustomerPayment,
  recordDelivery,
  setCustomerStatus,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * One customer, end to end (DEMO-009).
 *
 * The screen a dairy actually works from: what this household takes, what
 * arrived this week, what they owe, and what they have paid. The whole
 * workflow — record a delivery, raise the bill, take the money, hand over the
 * receipt — is reachable without leaving the page.
 *
 * Every figure is the platform's. The portal prints `amount`, `outstanding`
 * and the totals; it does not multiply a quantity by a rate and it does not
 * subtract payments from invoices. The one arithmetic-looking thing on the
 * page — the delivery preview under the quantity box — is deliberately absent
 * for that reason: the rate is agreed, the amount is computed on the server,
 * and a preview would be a second pricing engine.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;

const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Request failed";
};

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "—";

/** Today, in UTC — the platform's clock, not the browser's. */
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** The first and last day of the month a date falls in, in UTC. */
function monthBounds(day: string): { from: string; to: string } {
  const [y, m] = day.split("-").map(Number);
  const from = new Date(Date.UTC(y, m - 1, 1));
  const to = new Date(Date.UTC(y, m, 0));
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
}

export default function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<Load<CustomerDetail>>(LOADING);
  const [balance, setBalance] = useState<CustomerBalance | null>(null);
  const [deliveries, setDeliveries] = useState<DeliveryPageResult | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<CustomerPayment[]>([]);
  const [receipts, setReceipts] = useState<CustomerReceipt[]>([]);

  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail({ state: "ready", data: await getCustomer(id) });
    } catch (err) {
      setDetail({ state: "error", message: describe(err) });
      return;
    }
    // Everything below is context. None of it may blank the page.
    getCustomerBalance(id)
      .then(setBalance)
      .catch(() => setBalance(null));
    listDeliveries({ customer_id: id, limit: 30, offset: 0 })
      .then(setDeliveries)
      .catch(() => setDeliveries(null));
    listInvoices({ customer_id: id, limit: 12, offset: 0 })
      .then((p) => setInvoices(p.items ?? []))
      .catch(() => setInvoices([]));
    listCustomerPayments({ customer_id: id, limit: 12, offset: 0 })
      .then((p) => setPayments(p.items ?? []))
      .catch(() => setPayments([]));
    listCustomerReceipts({ customer_id: id, limit: 12, offset: 0 })
      .then((p) => setReceipts(p.items ?? []))
      .catch(() => setReceipts([]));
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  /** Act, then re-read — including after a refusal. */
  async function run(label: string, action: () => Promise<unknown>, success: string) {
    setBusy(label);
    setFailure(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
    } catch (err) {
      setFailure(describe(err));
    } finally {
      setBusy(null);
      await load();
    }
  }

  if (detail.state === "loading") return <LoadingState label="Loading customer…" />;
  if (detail.state === "error")
    return (
      <div className="mx-auto w-full max-w-6xl p-4 sm:p-6 lg:p-8">
        <ErrorState
          message={`This customer could not be loaded — ${detail.message}.`}
          action={
            <Link className="text-sm underline underline-offset-4" href="/customers">
              Back to customers
            </Link>
          }
        />
      </div>
    );

  const { customer, plans } = detail.data;
  const plan = plans.find((p) => p.active) ?? null;
  const currency = customer.currency;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[{ label: "Customers", href: "/customers" }, { label: customer.code }]}
        title={customer.name}
        description={[customer.code, customer.customer_type, customer.phone, customer.address]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <span className="inline-flex items-center gap-2">
            <StatusBadge status={customer.status} />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy !== null}
              onClick={() =>
                void run(
                  "status",
                  () =>
                    setCustomerStatus(
                      customer.id,
                      customer.status === "active" ? "inactive" : "active",
                    ),
                  customer.status === "active"
                    ? "Customer deactivated — no further deliveries can be recorded."
                    : "Customer reactivated.",
                )
              }
            >
              {customer.status === "active" ? "Deactivate" : "Reactivate"}
            </Button>
          </span>
        }
      />

      {notice ? (
        <p role="status" className="rounded-md bg-muted px-4 py-3 text-sm">
          {notice}
        </p>
      ) : null}
      {failure ? (
        <p role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          The platform refused: {failure}
        </p>
      ) : null}

      {/* --- the account, at a glance ------------------------------------- */}
      <section aria-label="Account" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Outstanding"
          value={balance ? <Money amount={balance.outstanding} currency={currency} /> : "—"}
          hint={balance ? `${balance.open_invoices} open invoice(s)` : undefined}
          icon={<Wallet className="size-4" />}
        />
        <StatTile
          label="Invoiced"
          value={balance ? <Money amount={balance.invoiced} currency={currency} /> : "—"}
        />
        <StatTile
          label="Paid"
          value={balance ? <Money amount={balance.paid} currency={currency} /> : "—"}
        />
        <StatTile
          label="Not yet billed"
          value={balance ? <Money amount={balance.unbilled_amount} currency={currency} /> : "—"}
          hint={
            balance ? `${balance.unbilled_deliveries} delivered, awaiting a bill` : undefined
          }
          icon={<Truck className="size-4" />}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* --- record a delivery ------------------------------------------ */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Record a delivery</CardTitle>
            <CardDescription>
              {plan ? (
                <>
                  Standing order <Quantity value={plan.default_quantity} unit={plan.quantity_unit} />{" "}
                  at {String(plan.unit_price)} {currency} per {plan.quantity_unit}. The amount is
                  computed by the platform from that rate — it is never typed here.
                </>
              ) : (
                "This customer has no delivery plan, so no delivery can be recorded yet."
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {plan ? (
              <RecordDeliveryForm
                customerId={customer.id}
                defaultQuantity={String(plan.default_quantity)}
                unit={plan.quantity_unit}
                busy={busy !== null}
                onDone={(message) => {
                  setNotice(message);
                  void load();
                }}
                onSubmit={(body) => recordDelivery(body)}
              />
            ) : (
              <EmptyState
                title="No delivery plan"
                description="Agree a quantity and rate with this customer before recording a delivery."
              />
            )}
          </CardContent>
        </Card>

        {/* --- the plan ---------------------------------------------------- */}
        <Card>
          <CardHeader>
            <CardTitle>Delivery plan</CardTitle>
            <CardDescription>
              A rate change supersedes the plan rather than editing it, so a delivery priced last
              week can still be explained.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {plans.length === 0 ? (
              <EmptyState title="No plan agreed" />
            ) : (
              <ul className="flex flex-col divide-y">
                {plans.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="flex flex-col">
                      <span className="text-sm">
                        {String(p.unit_price)} {p.currency}/{p.quantity_unit}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        from {p.effective_from} · <Quantity value={p.default_quantity} unit={p.quantity_unit} />
                      </span>
                    </div>
                    {p.active ? (
                      <StatusBadge status="active" />
                    ) : (
                      <span className="text-xs text-muted-foreground">superseded</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* --- delivery history -------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Delivery history</CardTitle>
          <CardDescription>
            {deliveries
              ? `${deliveries.total} deliveries — the totals below cover all of them, not this page.`
              : "The most recent deliveries to this customer."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!deliveries || deliveries.items.length === 0 ? (
            <EmptyState
              title="Nothing delivered yet"
              description="Record the first delivery above."
            />
          ) : (
            <>
              <div className="mb-3 flex flex-wrap gap-6 text-sm">
                <span>
                  <span className="text-muted-foreground">Total quantity </span>
                  <Quantity value={deliveries.total_quantity} unit="L" />
                </span>
                <span>
                  <span className="text-muted-foreground">Total value </span>
                  <Money amount={deliveries.total_amount} currency={currency} />
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Deliveries to {customer.name}</caption>
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Date</th>
                      <th className="py-2 pr-4 font-medium">Slot</th>
                      <th className="py-2 pr-4 text-right font-medium">Quantity</th>
                      <th className="py-2 pr-4 text-right font-medium">Rate</th>
                      <th className="py-2 pr-4 text-right font-medium">Amount</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 font-medium">Billed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.items.map((d: Delivery) => (
                      <tr key={d.id} className="border-b last:border-0">
                        <td className="py-2 pr-4 tabular-nums">{d.delivery_date}</td>
                        <td className="py-2 pr-4 text-muted-foreground">{d.slot}</td>
                        <td className="py-2 pr-4 text-right">
                          <Quantity value={d.quantity} unit={d.quantity_unit} />
                        </td>
                        <td className="py-2 pr-4 text-right tabular-nums">
                          {String(d.unit_price)}
                        </td>
                        <td className="py-2 pr-4 text-right">
                          <Money amount={d.amount} currency={d.currency} />
                        </td>
                        <td className="py-2 pr-4">
                          <StatusBadge status={d.status} />
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {d.invoice_id ? "on a bill" : "not yet billed"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* --- the monthly bill --------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly bills</CardTitle>
          <CardDescription>
            A bill is built from the period&apos;s unbilled deliveries. Issuing it is irreversible:
            it becomes the statement the customer is given.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <GenerateInvoiceForm
            busy={busy !== null}
            onGenerate={(from, to) =>
              void run(
                "invoice",
                () => generateInvoice({ customer_id: customer.id, period_from: from, period_to: to }),
                "Draft bill created from the period's unbilled deliveries.",
              )
            }
          />
          {invoices.length === 0 ? (
            <EmptyState title="No bills yet" />
          ) : (
            <ul className="flex flex-col divide-y">
              {invoices.map((inv) => (
                <li key={inv.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="flex flex-col">
                    <Link className="font-medium hover:underline" href={`/invoices/${inv.id}`}>
                      {inv.invoice_number}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {inv.period_from} → {inv.period_to} · {inv.line_count} deliveries
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Money amount={inv.amount_due} currency={inv.currency} />
                    <StatusBadge status={inv.status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* --- take money ------------------------------------------------- */}
        <Card>
          <CardHeader>
            <CardTitle>Payments received</CardTitle>
            <CardDescription>
              Money from the customer to the dairy. Applied to the oldest unpaid bill first.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <RecordPaymentForm
              busy={busy !== null}
              outstanding={balance ? String(balance.outstanding) : ""}
              currency={currency}
              onRecord={(amount, method, reference) =>
                void run(
                  "payment",
                  () =>
                    recordCustomerPayment({
                      customer_id: customer.id,
                      amount,
                      method,
                      reference,
                    }),
                  "Payment recorded. A receipt is generated from the platform's own event.",
                )
              }
            />
            {payments.length === 0 ? (
              <EmptyState title="No payments yet" />
            ) : (
              <ul className="flex flex-col divide-y">
                {payments.map((pay) => (
                  <li key={pay.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{pay.payment_number}</span>
                      <span className="text-xs text-muted-foreground">
                        {pay.method}
                        {pay.reference ? ` · ${pay.reference}` : ""} · {stamp(pay.received_at)}
                      </span>
                    </div>
                    <Money amount={pay.amount} currency={pay.currency} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* --- receipts ---------------------------------------------------- */}
        <Card>
          <CardHeader>
            <CardTitle>Receipts</CardTitle>
            <CardDescription>
              Generated by the platform from each recorded payment — never by this page, and never
              changed once issued.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {receipts.length === 0 ? (
              <EmptyState
                title="No receipts yet"
                description="A receipt appears shortly after a payment is recorded."
              />
            ) : (
              <ul className="flex flex-col divide-y">
                {receipts.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="flex flex-col">
                      <span className="inline-flex items-center gap-1.5 text-sm font-medium">
                        <ReceiptIcon aria-hidden className="size-3.5" />
                        {r.receipt_number}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {r.payment_number} · {stamp(r.generated_at)}
                        {r.applied_to ? ` · ${r.applied_to}` : ""}
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
    </div>
  );
}

function RecordDeliveryForm({
  customerId,
  defaultQuantity,
  unit,
  busy,
  onDone,
  onSubmit,
}: {
  customerId: string;
  defaultQuantity: string;
  unit: string;
  busy: boolean;
  onDone: (message: string) => void;
  onSubmit: (body: {
    customer_id: string;
    delivery_date: string;
    slot: string;
    quantity: string;
    status: string;
  }) => Promise<unknown>;
}) {
  const [day, setDay] = useState(today());
  const [slot, setSlot] = useState("morning");
  const [quantity, setQuantity] = useState(defaultQuantity);
  const [status, setStatus] = useState("delivered");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setWorking(true);
        setError(null);
        try {
          await onSubmit({
            customer_id: customerId,
            delivery_date: day,
            slot,
            quantity,
            status,
          });
          onDone(`Delivery recorded for ${day} (${slot}).`);
        } catch (err) {
          setError(describe(err));
        } finally {
          setWorking(false);
        }
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="d-date">Date</Label>
        <Input id="d-date" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="d-slot">Slot</Label>
        <select
          id="d-slot"
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          value={slot}
          onChange={(e) => setSlot(e.target.value)}
        >
          <option value="morning">morning</option>
          <option value="evening">evening</option>
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="d-qty">Quantity ({unit})</Label>
        <Input
          id="d-qty"
          className="w-32"
          inputMode="decimal"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="d-status">Outcome</Label>
        <select
          id="d-status"
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="delivered">delivered</option>
          <option value="skipped">skipped</option>
          <option value="returned">returned</option>
        </select>
      </div>
      <Button type="submit" disabled={busy || working}>
        {working ? "Recording…" : "Record delivery"}
      </Button>
      {error ? (
        <p role="alert" className="w-full text-sm text-destructive">
          The platform refused: {error}
        </p>
      ) : null}
    </form>
  );
}

function GenerateInvoiceForm({
  busy,
  onGenerate,
}: {
  busy: boolean;
  onGenerate: (from: string, to: string) => void;
}) {
  const bounds = monthBounds(today());
  const [from, setFrom] = useState(bounds.from);
  const [to, setTo] = useState(bounds.to);

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onGenerate(from, to);
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="i-from">Billing period from</Label>
        <Input id="i-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="i-to">to</Label>
        <Input id="i-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <Button type="submit" variant="outline" disabled={busy}>
        Generate bill
      </Button>
    </form>
  );
}

function RecordPaymentForm({
  busy,
  outstanding,
  currency,
  onRecord,
}: {
  busy: boolean;
  outstanding: string;
  currency: string;
  onRecord: (amount: string, method: string, reference: string) => void;
}) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<string>(CUSTOMER_PAYMENT_METHODS[0]);
  const [reference, setReference] = useState("");

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onRecord(amount, method, reference);
        setAmount("");
        setReference("");
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-amount">Amount ({currency})</Label>
        <Input
          id="p-amount"
          required
          inputMode="decimal"
          className="w-32"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder={outstanding}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-method">Method</Label>
        <select
          id="p-method"
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          {CUSTOMER_PAYMENT_METHODS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-ref">Reference</Label>
        <Input
          id="p-ref"
          className="w-44"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          placeholder="optional"
        />
      </div>
      <Button type="submit" disabled={busy || !amount}>
        Record payment
      </Button>
    </form>
  );
}
