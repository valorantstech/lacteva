"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Building2, CalendarClock, CreditCard } from "lucide-react";

import {
  ApiError,
  type EntitlementView,
  type SubscriptionView,
  getEntitlement,
  getSubscription,
} from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader, StatTile } from "@/components/page-header";

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

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "trialing"
      ? "bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-100"
      : status === "active"
        ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
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

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, e] = await Promise.all([getSubscription(), getEntitlement()]);
      setSubscription(s);
      setEntitlement(e);
    } catch (e) {
      setError(describe(e));
    }
  }, []);

  useEffect(() => {
    // Deferred by a tick, the idiom the rest of the portal uses: calling
    // setState synchronously in an effect body cascades a render.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  const remaining = entitlement?.trial_days_remaining ?? null;
  // On the trial plan — whether the window is still open or already closed.
  const onTrial = subscription?.plan_code === "LACTEVA_TRIAL";

  return (
    <div className="space-y-6">
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
            <StatTile
              label="Status"
              value={<StatusBadge status={entitlement.status} />}
              hint={subscription.plan_name}
              icon={<BadgeCheck className="size-4" />}
            />
            {/* An ended trial must still say WHEN it ended. Gating this on
                `status === "trialing"` hid the date at exactly the moment an
                administrator needs it most. */}
            <StatTile
              label={onTrial ? "Trial ends" : "Plan"}
              value={
                onTrial
                  ? (subscription.trial_ends_on ?? "—")
                  : subscription.plan_code
              }
              hint={
                onTrial && remaining !== null
                  ? remaining >= 0
                    ? `${remaining} day(s) remaining`
                    : `ended ${Math.abs(remaining)} day(s) ago`
                  : (subscription.current_period_end ?? undefined)
              }
              icon={<CalendarClock className="size-4" />}
            />
            <StatTile
              label="Collection centres"
              value={`${entitlement.active_centres} active`}
              hint={
                entitlement.centre_allowance === null
                  ? "unlimited during the trial"
                  : `${entitlement.subscribed_centres} subscribed`
              }
              icon={<Building2 className="size-4" />}
            />
            <StatTile
              label="Price"
              value={subscription.price ?? "—"}
              hint={
                subscription.price
                  ? `${subscription.currency_code} per ${subscription.billing_period}`
                  : "not yet published"
              }
              icon={<CreditCard className="size-4" />}
            />
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

              {/* No checkout: there is no payment provider to check out to, and
                  a button that pretended otherwise would be the one dishonest
                  thing on this page. */}
              <p className="text-muted-foreground">
                To change your plan or subscribe for more centres, contact
                Lacteva. Subscriptions are activated by the Lacteva team.
              </p>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
