"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import {
  type Driver,
  type Invitation,
  type Member,
  type Route,
  type User,
  driverDefaultRoutes,
  listDrivers,
  listInvitations,
  revokeCustomerBillLink,
  revokeInvitation,
  setDriverActive,
  setMemberStatus,
  updateRoute,
  describeError,
} from "@/lib/api";

/**
 * Departure is a checklist, so this is one (WO-88 §3).
 *
 * One panel that does the whole thing rather than leaving four jobs to
 * memory: suspend the membership (immediate — the platform re-checks it on
 * every request); withdraw any pending invitation for the address; if they
 * have a driver profile, retire it, and LIST the routes where they are the
 * default driver, refusing to finish until each has been handed to another
 * driver or had auto-planning switched off — the step that otherwise
 * produces a silent 5 a.m. failure; if they hold a household login, revoke
 * that household's bill link too, because a link outlives a login.
 *
 * A composition of existing calls. No new domain concept, no "archived user"
 * state, no soft-delete: a person who leaves is a suspended member with a
 * retired driver profile, and that is all. What will NOT change is written in
 * the panel itself.
 */
type Person = Member & { user: User | null };

type Plan = {
  invitations: Invitation[];
  driver: Driver | null;
  routes: Route[];
  otherDrivers: Driver[];
  customerId: string | null;
};

export function DepartureChecklist({
  person,
  onClose,
  onDone,
}: {
  person: Person;
  onClose: () => void;
  onDone: (summary: string) => Promise<void> | void;
}) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [handover, setHandover] = useState<Record<string, string>>({});

  const email = person.user?.email ?? null;
  const isCustomerLogin = (person.roles ?? []).some((r) => r.name === "CUSTOMER_PORTAL");
  const customerId = person.user?.customer_id ?? null;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [invitations, drivers] = await Promise.all([
          email ? listInvitations(email).catch(() => [] as Invitation[]) : Promise.resolve([]),
          listDrivers().catch(() => [] as Driver[]),
        ]);
        const driver = drivers.find((d) => d.user_id === person.user_id && d.active) ?? null;
        const routes = driver ? await driverDefaultRoutes(driver.id) : [];
        if (cancelled) return;
        setPlan({
          invitations,
          driver,
          routes,
          otherDrivers: drivers.filter((d) => d.active && d.id !== driver?.id),
          customerId: isCustomerLogin ? customerId : null,
        });
      } catch (err) {
        if (!cancelled) setError(describeError(err, "Could not read what this person holds"));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [email, person.user_id, isCustomerLogin, customerId]);

  /** The routes that would still be planned for them at 5 a.m. */
  const blocking = (plan?.routes ?? []).filter((r) => r.auto_plan);

  async function handOver(route: Route) {
    const to = handover[route.id];
    if (!to) return;
    setBusy(route.id);
    setError(null);
    try {
      await updateRoute(route.id, { default_driver_id: to });
      setPlan((p) => (p ? { ...p, routes: p.routes.filter((r) => r.id !== route.id) } : p));
    } catch (err) {
      setError(describeError(err, "Could not hand the route over"));
    } finally {
      setBusy(null);
    }
  }

  async function switchOff(route: Route) {
    setBusy(route.id);
    setError(null);
    try {
      await updateRoute(route.id, { auto_plan: false, clear_default_driver: true });
      setPlan((p) => (p ? { ...p, routes: p.routes.filter((r) => r.id !== route.id) } : p));
    } catch (err) {
      setError(describeError(err, "Could not switch auto-planning off"));
    } finally {
      setBusy(null);
    }
  }

  async function finish() {
    if (!plan || blocking.length > 0) return;
    setBusy("finish");
    setError(null);
    const done: string[] = [];
    try {
      // The membership first: it carries the refusal that matters (the last
      // administrator), and nothing else should happen if it is refused.
      await setMemberStatus(person.user_id, "suspended");
      done.push("membership suspended");
      for (const inv of plan.invitations) {
        await revokeInvitation(inv.id);
      }
      if (plan.invitations.length > 0)
        done.push(`${plan.invitations.length} pending invitation(s) withdrawn`);
      if (plan.driver) {
        await setDriverActive(plan.driver.id, false);
        done.push(`driver ${plan.driver.code} retired`);
      }
      if (plan.customerId) {
        await revokeCustomerBillLink(plan.customerId);
        done.push("the household's bill link revoked");
      }
      await onDone(
        `${person.user?.full_name ?? "The member"} has left: ${done.join(", ")}. ` +
          "Their name stays on everything they did.",
      );
    } catch (err) {
      setError(describeError(err, "The departure could not be completed"));
      setBusy(null);
    }
  }

  return (
    <section
      role="dialog"
      aria-modal="false"
      aria-labelledby="departure-title"
      data-testid="departure"
      className="flex flex-col gap-3 rounded-md border border-border bg-card p-4 text-sm"
    >
      <h2 id="departure-title" className="text-base font-semibold">
        Remove {person.user?.full_name ?? "this member"} from the organisation
      </h2>
      {error ? (
        <p role="alert" className="text-destructive">
          The platform refused: {error}
        </p>
      ) : null}
      {plan === null && !error ? (
        <p className="text-muted-foreground">Reading what this person holds…</p>
      ) : null}
      {plan ? (
        <>
          <ul className="list-disc pl-5" data-testid="departure-steps">
            <li>
              Suspend the membership — immediate; their very next request is refused,
              whatever session they hold.
            </li>
            {plan.invitations.length > 0 ? (
              <li>
                Withdraw {plan.invitations.length} pending invitation(s) for {email}.
              </li>
            ) : null}
            {plan.driver ? (
              <li>
                Retire driver profile <strong>{plan.driver.code}</strong> — no future run
                can be assigned to them.
              </li>
            ) : null}
            {plan.customerId ? (
              <li>Revoke the household&apos;s bill link — a link outlives a login.</li>
            ) : null}
          </ul>

          {plan.routes.length > 0 ? (
            <div className="flex flex-col gap-2" data-testid="departure-routes">
              <p>
                <strong>{plan.routes.length}</strong> route(s) still name them as the default
                driver. Hand each to another driver, or switch its auto-planning off — the
                nightly job would otherwise plan the round for a driver who has left.
              </p>
              <ul className="flex flex-col gap-2">
                {plan.routes.map((route) => (
                  <li
                    key={route.id}
                    className="flex flex-wrap items-center gap-2"
                    data-testid={`departure-route-${route.code}`}
                  >
                    <span className="font-medium">
                      {route.code} · {route.name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {route.auto_plan ? "auto-planned" : "not auto-planned"}
                    </span>
                    <Select
                      aria-label={`Hand ${route.code} to`}
                      className="h-8"
                      value={handover[route.id] ?? ""}
                      onChange={(e) => setHandover({ ...handover, [route.id]: e.target.value })}
                    >
                      <option value="">Hand to…</option>
                      {plan.otherDrivers.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.code} · {d.full_name}
                        </option>
                      ))}
                    </Select>
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy !== null || !handover[route.id]}
                      onClick={() => void handOver(route)}
                    >
                      Hand over
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busy !== null}
                      onClick={() => void switchOff(route)}
                    >
                      Switch auto-planning off
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="text-xs text-muted-foreground" data-testid="departure-unchanged">
            What will not change: their name stays on every delivery, run and audit line
            they made, and their deliveries are not reassigned to anyone. If they come
            back, reinstate this membership — the same login, with their history — rather
            than inviting them again.
          </p>

          <div className="flex gap-2">
            <Button
              type="button"
              variant="destructive"
              disabled={busy !== null || blocking.length > 0}
              onClick={() => void finish()}
              data-testid="departure-finish"
            >
              {busy === "finish" ? "Removing…" : "Remove from organisation"}
            </Button>
            <Button type="button" variant="ghost" disabled={busy === "finish"} onClick={onClose}>
              Not now
            </Button>
            {blocking.length > 0 ? (
              <span
                className="self-center text-xs text-muted-foreground"
                data-testid="departure-blocked"
              >
                {blocking.length} auto-planned route(s) still name them — hand over or switch off first.
              </span>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
