"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Building2, CalendarClock, CreditCard } from "lucide-react";

import {
  ApiError,
  type EntitlementView,
  type QuoteView,
  type SubscriptionPaymentView,
  type SubscriptionView,
  cancelSubscriptionCheckout,
  getEntitlement,
  getSubscription,
  getSubscriptionPayments,
  getSubscriptionQuote,
  refreshSubscriptionCheckout,
  startSubscriptionCheckout,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";

/**
 * The organization's commercial standing (DEMO-026).
 *
 * **Read-only, and every figure is the server's.** Status is derived on the
 * platform from stored dates on the organization's own clock; there is no
 * endpoint that accepts a status, so there is nothing here for a browser to
 * set. A screen that could move a subscription would be a screen that could
 * grant itself free software.
 *
 * Deliberately small. The work order asked for the minimum surface that lets
 * an administrator see where they stand — not a pricing page, and not a
 * checkout, because no payment provider exists to check out to.
 */

const describe = (e: unknown) => {
  if (e instanceof ApiError)
    return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Could not load the subscription";
};

const PAID_PLAN = "LACTEVA_STANDARD";

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "trialing"
      ? "bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-100"
      : status === "active"
        ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
        : status === "past_due"
          ? "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100"
          : "bg-muted text-muted-foreground";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}
    >
      <BadgeCheck className="h-3 w-3" />
      {status}
    </span>
  );
}

export default function SubscriptionPage() {
  const [subscription, setSubscription] = useState<SubscriptionView | null>(
    null,
  );
  const [entitlement, setEntitlement] = useState<EntitlementView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [payments, setPayments] = useState<SubscriptionPaymentView[]>([]);
  const [quote, setQuote] = useState<QuoteView | null>(null);
  const [centres, setCentres] = useState("1");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, e, p] = await Promise.all([
        getSubscription(),
        getEntitlement(),
        getSubscriptionPayments(),
      ]);
      setSubscription(s);
      setEntitlement(e);
      setPayments(p);
      // Seed the quantity from what the organization actually runs, so the
      // common case needs no typing and no arithmetic.
      setCentres(String(Math.max(e.active_centres, 1)));
    } catch (e) {
      setError(describe(e));
    }
  }, []);

  /** The AMOUNT is always the server's answer, re-asked whenever the quantity
   *  changes. Nothing here multiplies anything. */
  const requote = useCallback(async (quantity: number) => {
    if (!Number.isFinite(quantity) || quantity < 1) {
      setQuote(null);
      return;
    }
    try {
      setQuote(await getSubscriptionQuote(PAID_PLAN, quantity));
    } catch (e) {
      setQuote(null);
      setError(describe(e));
    }
  }, []);

  const act = useCallback(
    async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
      } catch (e) {
        setError(describe(e));
      } finally {
        setBusy(false);
        await load();
      }
    },
    [load],
  );

  useEffect(() => {
    // Deferred by a tick, the idiom the rest of the portal uses: calling
    // setState synchronously in an effect body cascades a render.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    const quantity = Number.parseInt(centres, 10);
    const timer = setTimeout(() => void requote(quantity), 150);
    return () => clearTimeout(timer);
  }, [centres, requote]);

  const remaining = entitlement?.trial_days_remaining ?? null;
  const openPayment = payments.find((p) => p.status === "pending") ?? null;
  // On the trial plan — whether the window is still open or already closed.
  const onTrial = subscription?.plan_code === "LACTEVA_TRIAL";

  return (
    <PageContainer width="default">
      <PageHeader
        title="Subscription"
        description="What this organization is entitled to use, and until when."
      />

      {error ? (
        <Card>
          <CardContent className="py-4 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      ) : null}

      {subscription && entitlement ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Surface
              tone="metric"
              className="flex items-start justify-between gap-3"
            >
              <Metric
                label="Status"
                value={<StatusBadge status={entitlement.status} />}
                caption={subscription.plan_name}
              />
              <span aria-hidden className="text-muted-foreground">
                <BadgeCheck className="size-4" />
              </span>
            </Surface>
            {/* An ended trial must still say WHEN it ended. Gating this on
                `status === "trialing"` hid the date at exactly the moment an
                administrator needs it most. */}
            <Surface
              tone="metric"
              className="flex items-start justify-between gap-3"
            >
              <Metric
                label={onTrial ? "Trial ends" : "Plan"}
                value={
                  onTrial
                    ? (subscription.trial_ends_on ?? "—")
                    : subscription.plan_code
                }
                caption={
                  onTrial && remaining !== null
                    ? remaining >= 0
                      ? `${remaining} day(s) remaining`
                      : `ended ${Math.abs(remaining)} day(s) ago`
                    : (subscription.current_period_end ?? undefined)
                }
              />
              <span aria-hidden className="text-muted-foreground">
                <CalendarClock className="size-4" />
              </span>
            </Surface>
            <Surface
              tone="metric"
              className="flex items-start justify-between gap-3"
            >
              <Metric
                label="Collection centres"
                value={`${entitlement.active_centres} active`}
                caption={
                  entitlement.centre_allowance === null
                    ? "unlimited during the trial"
                    : `${entitlement.subscribed_centres} subscribed`
                }
              />
              <span aria-hidden className="text-muted-foreground">
                <Building2 className="size-4" />
              </span>
            </Surface>
            <Surface
              tone="metric"
              className="flex items-start justify-between gap-3"
            >
              <Metric
                label="Price"
                value={subscription.price ?? "—"}
                caption={
                  subscription.price
                    ? `${subscription.currency_code} per ${subscription.billing_period}`
                    : "not yet published"
                }
              />
              <span aria-hidden className="text-muted-foreground">
                <CreditCard className="size-4" />
              </span>
            </Surface>
          </div>

          <Card>
            <CardContent className="space-y-3 py-4 text-sm">
              {entitlement.status === "trialing" ? (
                <p>
                  Your trial runs to{" "}
                  <strong>{subscription.trial_ends_on}</strong>. Every feature
                  is available and there is no limit on collection centres.
                </p>
              ) : null}

              {entitlement.can_operate ? null : (
                <p className="text-destructive">
                  This subscription has ended. Your records remain readable, and
                  activating a new collection centre is paused until a
                  subscription is in place.
                </p>
              )}

              {entitlement.within_centre_allowance ? null : (
                <p>
                  {entitlement.active_centres} centres are active and the
                  subscription covers {entitlement.centre_allowance}. Existing
                  centres keep working; activating another needs more subscribed
                  centres.
                </p>
              )}

              {entitlement.status === "past_due" ? (
                <p>
                  The last renewal did not go through. Everything keeps working
                  until <strong>{entitlement.grace_ends_on}</strong> — pay below
                  to clear it. Nothing has been deleted.
                </p>
              ) : null}
            </CardContent>
          </Card>

          {/* --- Paying, or the honest explanation of why not --------------
              There is no checkout button when the deployment cannot take
              money. A button that opened nothing would be the one dishonest
              thing on this page. */}
          <Card>
            <CardContent className="space-y-4 py-4 text-sm">
              <h2 className="font-medium">Subscribe</h2>

              {openPayment ? (
                <div className="space-y-3">
                  <p>
                    A payment of{" "}
                    <strong>
                      {openPayment.currency_code} {openPayment.amount}
                    </strong>{" "}
                    for {openPayment.quantity} collection centre(s) is awaiting
                    confirmation from the payment provider.
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    {openPayment.checkout_url ? (
                      <a
                        className="text-primary underline underline-offset-4"
                        href={openPayment.checkout_url}
                        rel="noreferrer noopener"
                        target="_blank"
                      >
                        Continue to the payment page
                      </a>
                    ) : null}
                    {/* "Check again" asks the SERVER to ask the provider. It
                        cannot report success on its own, which is why the label
                        is a question rather than a claim. */}
                    <Button
                      disabled={busy}
                      onClick={() => void act(refreshSubscriptionCheckout)}
                      size="sm"
                    >
                      Check payment status
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() => void act(cancelSubscriptionCheckout)}
                      size="sm"
                      variant="outline"
                    >
                      Cancel this payment
                    </Button>
                  </div>
                </div>
              ) : quote?.payable ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="space-y-1">
                      <span className="block text-xs text-muted-foreground">
                        Collection centres
                      </span>
                      <Input
                        className="w-32"
                        inputMode="numeric"
                        min={1}
                        onChange={(e) => setCentres(e.target.value)}
                        type="number"
                        value={centres}
                      />
                    </label>
                    <p className="pb-2">
                      {quote.unit_price} {quote.currency_code} per centre per{" "}
                      {quote.billing_period} ={" "}
                      <strong>
                        {quote.currency_code} {quote.amount}
                      </strong>
                    </p>
                  </div>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      void act(() =>
                        startSubscriptionCheckout(
                          PAID_PLAN,
                          Number.parseInt(centres, 10),
                        ),
                      )
                    }
                  >
                    Pay for {quote.quantity} centre(s)
                  </Button>
                  <p className="text-muted-foreground">
                    You are charged per collection centre. The amount is
                    calculated by Lacteva; this page never sets a price.
                  </p>
                </div>
              ) : (
                <p className="text-muted-foreground">
                  {quote?.payable_reason ??
                    "Online payment is not available on this deployment."}{" "}
                  To change your plan or subscribe for more centres, contact
                  Lacteva.
                </p>
              )}
            </CardContent>
          </Card>

          {payments.length ? (
            <Card>
              <CardContent className="py-4">
                <h2 className="mb-3 text-sm font-medium">Payment history</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="py-1 pr-4 font-medium">Date</th>
                        <th className="py-1 pr-4 font-medium">Amount</th>
                        <th className="py-1 pr-4 font-medium">Centres</th>
                        <th className="py-1 pr-4 font-medium">Status</th>
                        <th className="py-1 font-medium">Reference</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payments.map((payment) => (
                        <tr className="border-t border-border" key={payment.id}>
                          <td className="py-2 pr-4">
                            {payment.created_at.slice(0, 10)}
                          </td>
                          <td className="py-2 pr-4">
                            {payment.currency_code} {payment.amount}
                          </td>
                          <td className="py-2 pr-4">{payment.quantity}</td>
                          <td className="py-2 pr-4">
                            {payment.status}
                            {payment.failure_message ? (
                              <span className="block text-xs text-muted-foreground">
                                {payment.failure_message}
                              </span>
                            ) : null}
                          </td>
                          {/* The provider's own public id — what a support
                              conversation needs, and never a credential. */}
                          <td className="py-2 font-mono text-xs text-muted-foreground">
                            {payment.provider_reference ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </PageContainer>
  );
}
