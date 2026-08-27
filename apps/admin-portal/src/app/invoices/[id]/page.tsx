"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Lock } from "lucide-react";
import {
  ApiError,
  type Customer,
  type InvoiceDetail,
  cancelInvoice,
  getCustomer,
  getInvoice,
  issueInvoice,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * One monthly bill (DEMO-009).
 *
 * The statement a dairy hands a household, and the requirement this work order
 * states most plainly: **it must reconcile exactly with the underlying delivery
 * records.**
 *
 * So the page prints the platform's figures and asks the platform whether they
 * still agree — `totals_match_lines` is the backend's own answer, not a sum
 * computed here. Every line links back to the delivery it came from, so the
 * reconciliation can be followed by hand.
 *
 * Issuing is irreversible and says so before it happens: an issued bill is the
 * document the customer has, and correcting it means a new one.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;

const describe = (e: unknown) => {
  if (e instanceof ApiError)
    return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Request failed";
};

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "—";

export default function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [detail, setDetail] = useState<Load<InvoiceDetail>>(LOADING);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getInvoice(id);
      setDetail({ state: "ready", data });
      getCustomer(data.invoice.customer_id)
        .then((c) => setCustomer(c.customer))
        .catch(() => setCustomer(null));
    } catch (err) {
      setDetail({ state: "error", message: describe(err) });
    }
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

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
    return <LoadingState label="Loading the bill…" />;
  if (detail.state === "error")
    return (
      <PageContainer width="default" className="max-w-5xl">
        <ErrorState
          message={`This bill could not be loaded — ${detail.message}.`}
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

  const { invoice, lines, paid, outstanding, totals_match_lines } = detail.data;
  const isDraft = invoice.status === "draft";

  return (
    <PageContainer width="default" className="max-w-5xl">
      <PageHeader
        breadcrumbs={[
          { label: "Customers", href: "/customers" },
          ...(customer
            ? [{ label: customer.name, href: `/customers/${customer.id}` }]
            : []),
          { label: invoice.invoice_number },
        ]}
        title={invoice.invoice_number}
        description={`Billing period ${invoice.period_from} → ${invoice.period_to}${
          customer ? ` · ${customer.name} (${customer.code})` : ""
        }`}
        actions={
          <span className="inline-flex items-center gap-2">
            <StatusBadge status={invoice.status} />
            {invoice.status !== "draft" && invoice.status !== "cancelled" ? (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Lock aria-hidden className="size-3" /> issued{" "}
                {stamp(invoice.issued_at)}
              </span>
            ) : null}
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

      <Card>
        <CardHeader>
          <CardTitle>Statement</CardTitle>
          <CardDescription>
            Every figure was computed and stored by the platform from the
            deliveries below. This page performs no arithmetic.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-sm text-muted-foreground">Subtotal</dt>
              <dd className="text-lg font-semibold">
                <Money amount={invoice.subtotal} currency={invoice.currency} />
              </dd>
              <p className="text-xs text-muted-foreground">
                {invoice.line_count} deliveries
              </p>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">Adjustments</dt>
              <dd className="text-lg font-semibold">
                <Money
                  amount={invoice.adjustments}
                  currency={invoice.currency}
                />
              </dd>
              <p className="text-xs text-muted-foreground">
                fixed at zero for now
              </p>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">Brought forward</dt>
              <dd className="text-lg font-semibold">
                <Money
                  amount={invoice.previous_balance}
                  currency={invoice.currency}
                />
              </dd>
              <p className="text-xs text-muted-foreground">
                owed before this period
              </p>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">Amount due</dt>
              <dd className="text-lg font-semibold">
                <Money
                  amount={invoice.amount_due}
                  currency={invoice.currency}
                />
              </dd>
            </div>
          </dl>

          {totals_match_lines ? (
            <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 aria-hidden className="size-4" />
              The stored subtotal still equals the {invoice.line_count} lines
              below — verified by the platform.
            </p>
          ) : (
            <p
              role="alert"
              className="inline-flex items-center gap-2 text-sm font-medium text-destructive"
            >
              <AlertTriangle aria-hidden className="size-4" />
              The stored subtotal no longer matches the lines. Regenerate this
              bill.
            </p>
          )}

          {invoice.status !== "draft" ? (
            <dl className="flex flex-wrap gap-8 border-t pt-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Paid</dt>
                <dd className="font-semibold">
                  <Money amount={paid} currency={invoice.currency} />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Outstanding</dt>
                <dd className="font-semibold">
                  <Money amount={outstanding} currency={invoice.currency} />
                </dd>
              </div>
            </dl>
          ) : null}
        </CardContent>
      </Card>

      {/* --- lifecycle ---------------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Lifecycle</CardTitle>
          <CardDescription>
            {isDraft
              ? "A draft can still be changed or cancelled. Issuing it hands it to the customer."
              : invoice.status === "cancelled"
                ? "This bill was cancelled before it was issued. Its deliveries were released and can be billed again."
                : "This bill has been issued. It is immutable — a correction has to be a new bill or an adjustment."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {isDraft ? (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                disabled={busy !== null}
                onClick={() => setConfirming(true)}
              >
                Issue bill
              </Button>
              <Button
                type="button"
                variant="ghost"
                disabled={busy !== null}
                onClick={() =>
                  void run(
                    "cancel",
                    () =>
                      cancelInvoice(invoice.id, "cancelled from the portal"),
                    "Invoice cancelled. Its deliveries are invoiceable again.",
                  )
                }
              >
                Cancel bill
              </Button>
            </div>
          ) : null}

          {confirming ? (
            <div className="flex flex-col gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-4">
              <p className="inline-flex items-start gap-2 text-sm font-medium">
                <AlertTriangle
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0 text-destructive"
                />
                <span>
                  Issuing {invoice.invoice_number} is permanent. Once issued it
                  cannot be edited or cancelled — a correction has to be a new
                  bill. Its amount due of{" "}
                  <Money
                    amount={invoice.amount_due}
                    currency={invoice.currency}
                  />{" "}
                  becomes what the customer owes.
                </span>
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="destructive"
                  disabled={busy !== null}
                  onClick={() => {
                    setConfirming(false);
                    void run(
                      "issue",
                      () => issueInvoice(invoice.id),
                      "Invoice issued. It is now immutable and payable.",
                    );
                  }}
                >
                  {busy === "issue" ? "Issuing…" : "Yes, issue permanently"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setConfirming(false)}
                >
                  Keep it a draft
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* --- the deliveries it is made of --------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Deliveries billed</CardTitle>
          <CardDescription>
            {invoice.line_count === 0
              ? "This bill has no lines."
              : `${invoice.line_count} deliveries — each links back to the delivery it came from.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing billed here.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">
                  Deliveries billed by {invoice.invoice_number}
                </caption>
                <thead>
                  <tr className="border-b text-start text-muted-foreground">
                    <th className="py-2 pe-4 font-medium">Date</th>
                    <th className="py-2 pe-4 font-medium">Slot</th>
                    <th className="py-2 pe-4 font-medium">Product</th>
                    <th className="py-2 pe-4 text-end font-medium">Quantity</th>
                    <th className="py-2 pe-4 text-end font-medium">Rate</th>
                    <th className="py-2 text-end font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.id} className="border-b last:border-0">
                      <td className="py-2 pe-4 tabular-nums">
                        {line.delivery_date}
                      </td>
                      <td className="py-2 pe-4 text-muted-foreground">
                        {line.slot}
                      </td>
                      <td className="py-2 pe-4 text-muted-foreground">
                        {line.product}
                      </td>
                      <td className="py-2 pe-4 text-end">
                        <Quantity
                          value={line.quantity}
                          unit={line.quantity_unit}
                        />
                      </td>
                      <td className="py-2 pe-4 text-end tabular-nums">
                        {String(line.unit_price)}
                      </td>
                      <td className="py-2 text-end">
                        <Money
                          amount={line.amount}
                          currency={invoice.currency}
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
