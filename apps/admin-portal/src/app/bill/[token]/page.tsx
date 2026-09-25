"use client";

import { use, useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LactevaLockup } from "@/components/lockup";
import { Money } from "@/components/money";
import { StatusBadge } from "@/components/status-badge";
import { describeError, fetchPublicBill, type PublicBill } from "@/lib/api";

/**
 * A household's bills, opened from the link their dairy sent them (WO-86).
 *
 * Public, because the reader has no account and never needs one: the link is
 * the credential, and the platform decided whose bills it opens before a byte
 * of this page rendered. Everything shown is the platform's own answer —
 * balance, bills, receipts, statement — and the page adds no arithmetic.
 *
 * Deliberately English (Decision D-1, as `/accept-invitation`): a new,
 * unwired surface. The language work is one catalog away when it is wanted.
 *
 * Every dead link — expired, replaced, revoked, or never real — gets the same
 * sentence, because the platform gives them the same 404 and a household is
 * not owed the difference; it is owed a way forward, which is "ask the dairy".
 */
export default function PublicBillPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [bill, setBill] = useState<PublicBill | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPublicBill(token)
      .then((b) => {
        if (!cancelled) setBill(b);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            describeError(
              err,
              "Could not reach the platform. Check your connection and try again.",
            ),
          );
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="flex min-h-screen flex-col items-center gap-6 bg-[image:var(--gradient-cream-fresh)] p-4 sm:p-8">
      <LactevaLockup idPrefix="public-bill" className="lacteva-settle mt-4" />
      {error ? (
        <Card className="lacteva-settle w-full max-w-lg">
          <CardHeader>
            <CardTitle>This link does not open a bill</CardTitle>
            <CardDescription>
              It may have expired or been replaced by your dairy. Ask them for a
              new link.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p role="alert" className="text-sm text-muted-foreground">
              {error}
            </p>
          </CardContent>
        </Card>
      ) : bill === null ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading your bill…
        </p>
      ) : (
        <BillBody bill={bill} />
      )}
      <p className="max-w-lg text-center text-xs text-muted-foreground">
        This page is private to whoever holds its link. If you did not expect
        it, or the link has been shared further than you meant, ask your dairy
        to replace it.
      </p>
    </div>
  );
}

function BillBody({ bill }: { bill: PublicBill }) {
  const currency = bill.currency;
  const outstanding = bill.balance.outstanding;
  return (
    <main
      aria-label="Your bill"
      className="lacteva-settle flex w-full max-w-lg flex-col gap-4"
    >
      <Card>
        <CardHeader>
          <CardDescription>{bill.organization}</CardDescription>
          {/* WO-83 §2a: the head of the bill — where the dairy is and how to reach it. */}
          {bill.organization_address || bill.organization_phone ? (
            <CardDescription data-testid="public-bill-head">
              {[bill.organization_address, bill.organization_phone]
                .filter(Boolean)
                .join(" · ")}
            </CardDescription>
          ) : null}
          <CardTitle>{bill.customer.name}</CardTitle>
          <CardDescription>
            {[bill.customer.code, bill.customer.address]
              .filter(Boolean)
              .join(" · ")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-1">
          <span className="text-sm text-muted-foreground">
            {Number(outstanding) < 0 ? "Advance held" : "You owe"}
          </span>
          <span className="text-3xl font-semibold" data-testid="public-bill-outstanding">
            <Money
              amount={Math.abs(Number(outstanding)).toFixed(2)}
              currency={currency}
            />
          </span>
          <span className="text-xs text-muted-foreground">
            {bill.balance.open_invoices} open invoice(s) · not yet billed{" "}
            <Money amount={bill.balance.unbilled_amount} currency={currency} />
          </span>
          {/* WO-83 §2: how to pay, exactly as the dairy wrote it. */}
          {bill.pay_to ? (
            <p className="mt-2 text-sm" data-testid="public-bill-pay-to">
              <span className="text-muted-foreground">Pay to: </span>
              {bill.pay_to}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your invoices</CardTitle>
          <CardDescription>
            Every invoice your dairy has issued, newest first, with the receipts
            that paid it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {bill.invoices.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No invoice has been issued yet.
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {bill.invoices.map((invoice) => (
                <li
                  key={invoice.id}
                  className="flex flex-col gap-1 py-3"
                  data-testid={`public-invoice-${invoice.invoice_number}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{invoice.invoice_number}</span>
                    <span className="inline-flex items-center gap-2">
                      <Money amount={invoice.amount_due} currency={currency} />
                      <StatusBadge status={invoice.status} />
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {invoice.period_from} to {invoice.period_to} ·{" "}
                    {invoice.line_count} line(s)
                  </span>
                  {invoice.receipts.length > 0 ? (
                    <ul className="mt-1 flex flex-col gap-0.5 text-xs text-muted-foreground">
                      {invoice.receipts.map((receipt) => (
                        <li key={receipt.id}>
                          Receipt {receipt.receipt_number} ·{" "}
                          <Money amount={receipt.amount} currency={currency} />{" "}
                          · {receipt.method}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">This month</CardTitle>
          <CardDescription>
            {bill.statement.date_from} to {bill.statement.date_to}:{" "}
            {Number(bill.statement.opening_balance) < 0 ? "advance" : "opening"}{" "}
            <Money
              amount={Math.abs(Number(bill.statement.opening_balance)).toFixed(2)}
              currency={currency}
            />
            , billed <Money amount={bill.statement.billed} currency={currency} />
            , paid <Money amount={bill.statement.paid} currency={currency} />,
            closing{" "}
            <Money amount={bill.statement.closing_balance} currency={currency} />
            .
          </CardDescription>
        </CardHeader>
        {bill.statement.entries.length > 0 ? (
          <CardContent>
            <ul className="flex flex-col divide-y text-sm">
              {bill.statement.entries.map((entry, index) => (
                <li
                  key={`${entry.reference}-${index}`}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <span className="flex flex-col">
                    <span>
                      {entry.kind === "payment" ? "Payment" : "Invoice"}{" "}
                      {entry.reference}
                      {entry.receipt_number ? (
                        <span className="text-muted-foreground">
                          {" "}
                          · receipt {entry.receipt_number}
                        </span>
                      ) : null}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {entry.entry_date} · {entry.detail}
                    </span>
                  </span>
                  <span className="text-right">
                    {entry.kind === "payment" ? (
                      <>
                        −<Money amount={entry.credit} currency={currency} />
                      </>
                    ) : (
                      <Money amount={entry.debit} currency={currency} />
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        ) : null}
      </Card>
    </main>
  );
}
