"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Receipt as ReceiptIcon, Truck, Wallet } from "lucide-react";
import {
  CUSTOMER_PAYMENT_METHODS,
  type CustomerBalance,
  type CustomerDetail,
  type CustomerPayment,
  type CustomerStatement,
  type DeliveryPlan,
  type CustomerReceipt,
  type Delivery,
  type DeliveryPageResult,
  type Invoice,
  generateInvoice,
  getCustomer,
  getCustomerBalance,
  getCustomerStatement,
  pauseDeliveryPlan,
  setDeliveryPlan,
  resumeDeliveryPlan,
  listCustomerPayments,
  listCustomerReceipts,
  listDeliveries,
  listInvoices,
  recordCustomerPayment,
  recordDelivery,
  setCustomerStatus,
  updateCustomer,
  describeError,
} from "@/lib/api";
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
import { Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { useBusinessToday } from "@/components/date-range";
import { useLocale } from "@/lib/i18n";

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

const describe = (e: unknown) => describeError(e);

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "—";

/** The first and last day of the month a date falls in. Pure calendar
 *  arithmetic on an already-local date, so no clock is involved. */
function monthBounds(day: string): { from: string; to: string } {
  const [y, m] = day.split("-").map(Number);
  const from = new Date(Date.UTC(y, m - 1, 1));
  const to = new Date(Date.UTC(y, m, 0));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

export default function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { t } = useLocale();
  const [detail, setDetail] = useState<Load<CustomerDetail>>(LOADING);
  const [balance, setBalance] = useState<CustomerBalance | null>(null);
  const [deliveries, setDeliveries] = useState<DeliveryPageResult | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<CustomerPayment[]>([]);
  const [receipts, setReceipts] = useState<CustomerReceipt[]>([]);
  const [statement, setStatement] = useState<CustomerStatement | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  // Which correction panel is open, if any. A customer record used to be
  // write-once in this portal; these are the two things an operator needs to
  // change about a live customer.
  const [panel, setPanel] = useState<"none" | "details" | "plan">("none");

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
    // No dates: the platform answers for the DAIRY's current month. A browser
    // cannot compute a local month without a timezone database, and asking is
    // both cheaper and right (DEMO-013).
    getCustomerStatement(id)
      .then(setStatement)
      .catch(() => setStatement(null));
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  /** Act, then re-read — including after a refusal. */
  async function run(
    label: string,
    action: () => Promise<unknown>,
    success: string,
  ) {
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

  if (detail.state === "loading")
    return <LoadingState label="Loading customer…" />;
  if (detail.state === "error")
    return (
      <PageContainer width="default">
        <ErrorState
          message={`This customer could not be loaded — ${detail.message}.`}
          action={
            <Link
              className="text-sm underline underline-offset-4"
              href="/customers"
            >
              Back to customers
            </Link>
          }
        />
      </PageContainer>
    );

  const { customer, plans } = detail.data;
  const plan = plans.find((p) => p.active) ?? null;
  const currency = customer.currency;

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[
          { label: "Customers", href: "/customers" },
          { label: customer.code },
        ]}
        title={customer.name}
        description={[
          customer.code,
          customer.customer_type,
          customer.phone,
          customer.address,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={
          <span className="inline-flex flex-wrap items-center gap-2">
            <StatusBadge status={customer.status} />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy !== null}
              onClick={() => setPanel(panel === "details" ? "none" : "details")}
            >
              Edit details
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy !== null}
              onClick={() => setPanel(panel === "plan" ? "none" : "plan")}
            >
              Change order
            </Button>
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
        <p
          role="alert"
          className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          The platform refused: {failure}
        </p>
      ) : null}

      {panel === "details" ? (
        <EditCustomerCard
          customer={customer}
          busy={busy !== null}
          onCancel={() => setPanel("none")}
          onSaved={(message) => {
            setPanel("none");
            setNotice(message);
            void load();
          }}
          onFailed={setFailure}
        />
      ) : null}

      {panel === "plan" ? (
        <ChangePlanCard
          customerId={customer.id}
          current={plan}
          currency={currency}
          busy={busy !== null}
          onCancel={() => setPanel("none")}
          onSaved={(message) => {
            setPanel("none");
            setNotice(message);
            void load();
          }}
          onFailed={setFailure}
        />
      ) : null}

      {/* --- the account, at a glance ------------------------------------- */}
      <section
        aria-label="Account"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Outstanding"
            value={
              balance ? (
                <Money amount={balance.outstanding} currency={currency} />
              ) : (
                "—"
              )
            }
            caption={
              balance ? `${balance.open_invoices} open invoice(s)` : undefined
            }
          />
          <span aria-hidden className="text-muted-foreground">
            <Wallet className="size-4" />
          </span>
        </Surface>
        <Surface tone="metric">
          <Metric
            label="Invoiced"
            value={
              balance ? (
                <Money amount={balance.invoiced} currency={currency} />
              ) : (
                "—"
              )
            }
          />
        </Surface>
        <Surface tone="metric">
          <Metric
            label="Paid"
            value={
              balance ? (
                <Money amount={balance.paid} currency={currency} />
              ) : (
                "—"
              )
            }
          />
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Not yet billed"
            value={
              balance ? (
                <Money amount={balance.unbilled_amount} currency={currency} />
              ) : (
                "—"
              )
            }
            caption={
              balance
                ? `${balance.unbilled_deliveries} delivered, awaiting a bill`
                : undefined
            }
          />
          <span aria-hidden className="text-muted-foreground">
            <Truck className="size-4" />
          </span>
        </Surface>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* --- record a delivery ------------------------------------------ */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Record a delivery</CardTitle>
            <CardDescription>
              {plan ? (
                <>
                  Standing order{" "}
                  <Quantity
                    value={plan.default_quantity}
                    unit={plan.quantity_unit}
                  />{" "}
                  at {String(plan.unit_price)} {currency} per{" "}
                  {plan.quantity_unit}. The amount is computed by the platform
                  from that rate — it is never typed here.
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

        {/* --- the standing order (DEMO-016) ------------------------------- */}
        <Card>
          <CardHeader>
            <CardTitle>{t("plan.title")}</CardTitle>
            <CardDescription>{t("plan.subtitle")}</CardDescription>
          </CardHeader>
          <CardContent>
            {plans.length === 0 ? (
              <EmptyState
                title={t("plan.none")}
                description={t("plan.noneDetail")}
              />
            ) : (
              <ul className="flex flex-col divide-y">
                {plans.map((p) => (
                  <li key={p.id} className="flex flex-col gap-2 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex flex-col">
                        <span className="text-sm">
                          <Quantity
                            value={p.default_quantity}
                            unit={p.quantity_unit}
                          />
                          {" · "}
                          {String(p.unit_price)} {p.currency}/{p.quantity_unit}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {/* The platform sends a KEY for the schedule, never a
                              sentence — so this line is Hindi when the reader is. */}
                          {t(p.schedule_key ?? "schedule.daily")} ·{" "}
                          {t("plan.startDate")} {p.effective_from}
                          {p.effective_to
                            ? ` · ${t("plan.endDate")} ${p.effective_to}`
                            : ""}
                        </span>
                        {p.active && p.paused_from ? (
                          <span className="mt-1 text-xs font-medium text-amber-700 dark:text-amber-500">
                            {p.paused_to
                              ? t("plan.pausedUntil", { date: p.paused_to })
                              : t("plan.pausedIndefinitely")}
                          </span>
                        ) : null}
                        {p.active && !p.paused_from && p.next_delivery ? (
                          <span className="mt-1 text-xs text-muted-foreground">
                            {t("plan.nextDelivery")}: {p.next_delivery}
                          </span>
                        ) : null}
                      </div>
                      {p.active ? (
                        <StatusBadge
                          status={p.paused_from ? "paused" : "active"}
                        />
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {t("plan.superseded")}
                        </span>
                      )}
                    </div>
                    {p.active ? (
                      <PlanControls
                        plan={p}
                        busy={busy === p.id}
                        onPause={async (from, to) => {
                          setBusy(p.id);
                          try {
                            await pauseDeliveryPlan(p.id, {
                              paused_from: from,
                              paused_to: to || null,
                            });
                            setNotice(t("plan.paused"));
                            await load();
                          } catch (err) {
                            setFailure(describe(err));
                          } finally {
                            setBusy(null);
                          }
                        }}
                        onResume={async () => {
                          setBusy(p.id);
                          try {
                            await resumeDeliveryPlan(p.id);
                            setNotice(t("plan.resume"));
                            await load();
                          } catch (err) {
                            setFailure(describe(err));
                          } finally {
                            setBusy(null);
                          }
                        }}
                      />
                    ) : null}
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
                  <caption className="sr-only">
                    Deliveries to {customer.name}
                  </caption>
                  <thead>
                    <tr className="border-b text-start text-muted-foreground">
                      <th className="py-2 pe-4 font-medium">Date</th>
                      <th className="py-2 pe-4 font-medium">Slot</th>
                      <th className="py-2 pe-4 text-end font-medium">
                        Quantity
                      </th>
                      <th className="py-2 pe-4 text-end font-medium">Rate</th>
                      <th className="py-2 pe-4 text-end font-medium">Amount</th>
                      <th className="py-2 pe-4 font-medium">Status</th>
                      <th className="py-2 font-medium">Invoiced</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.items.map((d: Delivery) => (
                      <tr key={d.id} className="border-b last:border-0">
                        <td className="py-2 pe-4 tabular-nums">
                          {d.delivery_date}
                        </td>
                        <td className="py-2 pe-4 text-muted-foreground">
                          {d.slot}
                        </td>
                        <td className="py-2 pe-4 text-end">
                          <Quantity value={d.quantity} unit={d.quantity_unit} />
                        </td>
                        <td className="py-2 pe-4 text-end tabular-nums">
                          {String(d.unit_price)}
                        </td>
                        <td className="py-2 pe-4 text-end">
                          <Money amount={d.amount} currency={d.currency} />
                        </td>
                        <td className="py-2 pe-4">
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

      {/* --- how the balance came about ------------------------------------ */}
      {statement ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("statement.title")}</CardTitle>
            <CardDescription>
              {t("statement.subtitle")} — {statement.date_from} →{" "}
              {statement.date_to}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-5">
              <Surface tone="metric">
                <Metric
                  label={t("statement.opening")}
                  value={
                    <Money
                      amount={statement.opening_balance}
                      currency={statement.currency}
                    />
                  }
                />
              </Surface>
              {statement.delivered_quantity !== undefined ? (
                <Surface tone="metric">
                  <Metric
                    label={t("statement.milk")}
                    value={
                      <Quantity
                        value={statement.delivered_quantity}
                        unit={statement.quantity_unit ?? "L"}
                      />
                    }
                  />
                </Surface>
              ) : null}
              <Surface tone="metric">
                <Metric
                  label={t("statement.billed")}
                  value={
                    <Money
                      amount={statement.billed}
                      currency={statement.currency}
                    />
                  }
                />
              </Surface>
              <Surface tone="metric">
                <Metric
                  label={t("statement.paid")}
                  value={
                    <Money
                      amount={statement.paid}
                      currency={statement.currency}
                    />
                  }
                />
              </Surface>
              <Surface tone="metric">
                <Metric
                  label={t("statement.closing")}
                  value={
                    <Money
                      amount={statement.closing_balance}
                      currency={statement.currency}
                    />
                  }
                />
              </Surface>
            </div>

            {statement.entries.length === 0 ? (
              <EmptyState title={t("statement.empty")} />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">{t("statement.title")}</caption>
                  <thead>
                    <tr className="border-b text-start text-muted-foreground">
                      <th className="py-2 pe-4 font-medium">
                        {t("field.date")}
                      </th>
                      <th className="py-2 pe-4 font-medium">
                        {t("statement.entry")}
                      </th>
                      <th className="py-2 pe-4 text-end font-medium">
                        {t("statement.debit")}
                      </th>
                      <th className="py-2 pe-4 text-end font-medium">
                        {t("statement.credit")}
                      </th>
                      <th className="py-2 text-end font-medium">
                        {t("statement.runningBalance")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {statement.entries.map((entry) => (
                      <tr
                        key={`${entry.kind}-${entry.reference}`}
                        className="border-b last:border-0"
                      >
                        <td className="py-2 pe-4 tabular-nums">
                          {entry.entry_date}
                        </td>
                        <td className="py-2 pe-4">
                          <span className="font-medium">
                            {entry.kind === "invoice"
                              ? t("statement.invoice")
                              : t("statement.payment")}
                          </span>{" "}
                          <span className="text-muted-foreground">
                            {entry.reference}
                          </span>
                          <div className="text-xs text-muted-foreground">
                            {entry.detail}
                          </div>
                        </td>
                        <td className="py-2 pe-4 text-end">
                          {Number(entry.debit) === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <Money
                              amount={entry.debit}
                              currency={statement.currency}
                            />
                          )}
                        </td>
                        <td className="py-2 pe-4 text-end">
                          {Number(entry.credit) === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <Money
                              amount={entry.credit}
                              currency={statement.currency}
                            />
                          )}
                        </td>
                        <td className="py-2 text-end font-medium">
                          <Money
                            amount={entry.balance}
                            currency={statement.currency}
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
      ) : null}

      {/* --- the monthly bill --------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly bills</CardTitle>
          <CardDescription>
            A bill is built from the period&apos;s unbilled deliveries. Issuing
            it is irreversible: it becomes the statement the customer is given.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <GenerateInvoiceForm
            busy={busy !== null}
            onGenerate={(from, to) =>
              void run(
                "invoice",
                () =>
                  generateInvoice({
                    customer_id: customer.id,
                    period_from: from,
                    period_to: to,
                  }),
                "Draft bill created from the period's unbilled deliveries.",
              )
            }
          />
          {invoices.length === 0 ? (
            <EmptyState title="No bills yet" />
          ) : (
            <ul className="flex flex-col divide-y">
              {invoices.map((inv) => (
                <li
                  key={inv.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="flex flex-col">
                    <Link
                      className="font-medium hover:underline"
                      href={`/invoices/${inv.id}`}
                    >
                      {inv.invoice_number}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {inv.period_from} → {inv.period_to} · {inv.line_count}{" "}
                      deliveries
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
              Money from the customer to the dairy. Applied to the oldest unpaid
              bill first.
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
                  <li
                    key={pay.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {pay.payment_number}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {pay.method}
                        {pay.reference ? ` · ${pay.reference}` : ""} ·{" "}
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

        {/* --- receipts ---------------------------------------------------- */}
        <Card>
          <CardHeader>
            <CardTitle>Receipts</CardTitle>
            <CardDescription>
              Generated by the platform from each recorded payment — never by
              this page, and never changed once issued.
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
                  <li
                    key={r.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
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
    </PageContainer>
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
  // The DAIRY's today, not UTC's. An operator in Bengaluru recording the
  // morning round before 05:30 IST would otherwise have the form propose
  // yesterday's date — and a delivery filed a day early is a delivery on the
  // wrong month's bill.
  // Derived, not captured: this form can mount before the shell knows the
  // organization, and a stored default freezes the UTC fallback (DEMO-019).
  const businessToday = useBusinessToday();
  const [chosenDay, setChosenDay] = useState<string | null>(null);
  const day = chosenDay ?? businessToday;
  const setDay = setChosenDay;
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
        <Input
          id="d-date"
          type="date"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="d-slot">Slot</Label>
        <Select
          id="d-slot"
          value={slot}
          onChange={(e) => setSlot(e.target.value)}
        >
          <option value="morning">morning</option>
          <option value="evening">evening</option>
        </Select>
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
        <Select
          id="d-status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="delivered">delivered</option>
          <option value="skipped">skipped</option>
          <option value="returned">returned</option>
        </Select>
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
  // The billing period defaults to the DAIRY's current month and is derived
  // rather than captured: this form can mount before the shell knows the
  // organization, and a stored default would freeze the UTC fallback into the
  // period a manager is offered (DEMO-019).
  const bounds = monthBounds(useBusinessToday());
  const [chosen, setChosen] = useState<{ from: string; to: string } | null>(
    null,
  );
  const from = chosen?.from ?? bounds.from;
  const to = chosen?.to ?? bounds.to;
  const setFrom = (value: string) => setChosen({ from: value, to });
  const setTo = (value: string) => setChosen({ from, to: value });

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
        <Input
          id="i-from"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="i-to">to</Label>
        <Input
          id="i-to"
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
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
        <Select
          id="p-method"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          {CUSTOMER_PAYMENT_METHODS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
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

/**
 * Pause and resume, on one plan.
 *
 * The dates go to the SERVER as written: this component decides nothing about
 * which days are affected, it only collects two dates and posts them. What a
 * pause means — inclusive at both ends, no end meaning "until further notice"
 * — is `schedule.py`'s answer, and duplicating that reading here is how the
 * screen and the generator would eventually disagree about a holiday.
 */
function PlanControls({
  plan,
  busy,
  onPause,
  onResume,
}: {
  plan: DeliveryPlan;
  busy: boolean;
  onPause: (from: string, to: string) => Promise<void>;
  onResume: () => Promise<void>;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const businessToday = useBusinessToday();
  const [chosenFrom, setChosenFrom] = useState<string | null>(null);
  const from = chosenFrom ?? businessToday;
  const setFrom = setChosenFrom;
  const [to, setTo] = useState("");

  if (plan.paused_from) {
    return (
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void onResume()}
        >
          {t("plan.resume")}
        </Button>
        <span className="text-xs text-muted-foreground">
          {t("plan.paused_notice")}
        </span>
      </div>
    );
  }

  if (!open) {
    return (
      <Button
        size="sm"
        variant="ghost"
        className="self-start"
        onClick={() => setOpen(true)}
      >
        {t("plan.pause")}
      </Button>
    );
  }

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        await onPause(from, to);
        setOpen(false);
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`pause-from-${plan.id}`}>{t("plan.pauseFrom")}</Label>
        <input
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          id={`pause-from-${plan.id}`}
          type="date"
          required
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`pause-to-${plan.id}`}>{t("plan.pauseTo")}</Label>
        <input
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          id={`pause-to-${plan.id}`}
          type="date"
          value={to}
          min={from}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>
      <Button size="sm" type="submit" disabled={busy}>
        {t("plan.pause")}
      </Button>
      <Button
        size="sm"
        type="button"
        variant="ghost"
        onClick={() => setOpen(false)}
      >
        {t("action.cancel")}
      </Button>
    </form>
  );
}

/**
 * Correcting a customer's own details.
 *
 * The platform has always accepted `PUT /v1/customers/{id}`; nothing in the
 * portal ever called it, so a customer record was write-once — a phone number
 * typed wrong at registration stayed wrong. This is the missing caller, not a
 * new capability, and it sends the command the API already defines.
 */
function EditCustomerCard({
  customer,
  busy,
  onCancel,
  onSaved,
  onFailed,
}: {
  customer: CustomerDetail["customer"];
  busy: boolean;
  onCancel: () => void;
  onSaved: (message: string) => void;
  onFailed: (message: string) => void;
}) {
  const [name, setName] = useState(customer.name ?? "");
  const [type, setType] = useState(customer.customer_type ?? "household");
  const [phone, setPhone] = useState(customer.phone ?? "");
  const [address, setAddress] = useState(customer.address ?? "");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await updateCustomer(customer.id, {
        name: name.trim(),
        customer_type: type,
        phone: phone.trim(),
        address: address.trim(),
      });
      onSaved("Customer details updated.");
    } catch (err) {
      onFailed(describe(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Edit details</CardTitle>
        <CardDescription>
          Name, type, phone and address. The standing order is changed
          separately, because re-agreeing a rate is a different decision.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                required
                minLength={2}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="edit-type">Type</Label>
              <Select
                id="edit-type"
                value={type}
                onChange={(e) => setType(e.target.value)}
              >
                <option value="household">household</option>
                <option value="shop">shop</option>
                <option value="hotel">hotel</option>
                <option value="institution">institution</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="edit-phone">Phone</Label>
              <Input
                id="edit-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="edit-address">Address</Label>
              <Input
                id="edit-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving || busy}>
              {saving ? "Saving…" : "Save details"}
            </Button>
            <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/**
 * Re-agreeing the standing order.
 *
 * The plan is the single lever on what a customer receives and what they are
 * charged: `generate_deliveries` reads its quantity, price, weekdays and slot.
 * The portal could pause and resume one but never change it, so a household
 * moving from one litre to two, or a rate renegotiated, had nowhere to go —
 * and every delivery and invoice after that point was generated from the old
 * agreement.
 *
 * `POST /v1/customers/{id}/plan` SUPERSEDES rather than edits, per slot, so a
 * delivery priced last week still points at the plan that priced it. That is
 * the platform's rule and this form does not soften it — the copy says so,
 * because an operator who thinks they are editing history will be surprised
 * later.
 */
function ChangePlanCard({
  customerId,
  current,
  currency,
  busy,
  onCancel,
  onSaved,
  onFailed,
}: {
  customerId: string;
  current: DeliveryPlan | null;
  currency: string;
  busy: boolean;
  onCancel: () => void;
  onSaved: (message: string) => void;
  onFailed: (message: string) => void;
}) {
  const [quantity, setQuantity] = useState(
    current ? String(current.default_quantity) : "2.000",
  );
  const [rate, setRate] = useState(current ? String(current.unit_price) : "");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      // The money leaves as the operator typed it. `unit_price` is a decimal
      // string end to end; putting it through Number() here would lose the
      // platform's precision before the request was even made.
      await setDeliveryPlan(customerId, {
        product: current?.product ?? "RAW-COW-MILK",
        default_quantity: quantity.trim(),
        quantity_unit: current?.quantity_unit ?? "L",
        unit_price: rate.trim(),
        ...(current?.slot ? { slot: current.slot } : {}),
        ...(current?.weekdays ? { weekdays: current.weekdays } : {}),
      });
      onSaved("Standing order updated. Deliveries from now on use the new agreement.");
    } catch (err) {
      onFailed(describe(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Change the standing order</CardTitle>
        <CardDescription>
          This supersedes the current agreement rather than editing it, so
          deliveries already priced keep pointing at the plan that priced them.
          {current ? null : " This customer has no plan yet."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="plan-quantity">
                Quantity per delivery ({current?.quantity_unit ?? "L"})
              </Label>
              <Input
                id="plan-quantity"
                required
                inputMode="decimal"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="plan-rate">
                Agreed rate ({currency} per {current?.quantity_unit ?? "L"})
              </Label>
              <Input
                id="plan-rate"
                required
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving || busy}>
              {saving ? "Saving…" : "Agree new order"}
            </Button>
            <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
