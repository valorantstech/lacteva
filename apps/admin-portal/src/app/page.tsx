"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Banknote, Droplets, Handshake, Truck, Users } from "lucide-react";
import { type Session, getSession } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

// PORTAL-001 / F-11: same-origin, through the portal's own proxy. The
// browser no longer knows — or needs to know — where the platform lives.
const API = "/api/proxy";

/**
 * DEMO-001: every figure on this page is COMPUTED BY THE PLATFORM.
 *
 * The previous dashboard counted rows by asking five list endpoints for
 * `total`, which is fine for "how many suppliers" and useless for "how much
 * milk, worth what". Those answers are aggregations over money and quantity,
 * and the platform already has them in `/v1/reports/*` — where the sums are
 * exact `Decimal` inside the database rather than added up in a browser.
 *
 * So this page fetches summaries and renders them. It does not add, average,
 * convert or round anything. `payable_by_currency` arrives as a map of exact
 * decimal STRINGS and is displayed as sent.
 */

type DailySummary = {
  date_from: string;
  date_to: string;
  transactions: number;
  accepted: number;
  rejected: number;
  in_progress: number;
  suppliers_served: number;
  total_net_weight_kg: number;
  payable_by_currency: Record<string, string>;
  weighted_avg_fat: number | null;
};

type SettlementStatusRow = { status: string; count: number };
type SettlementSummary = {
  by_status: SettlementStatusRow[];
  finalized_net_total: string;
  total_settlements: number;
  total_lines: number;
};

type Readiness = { status: string; platform_status?: string; checks: Record<string, string> };

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { credentials: "same-origin", cache: "no-store" });
  // DASH-001: check the STATUS before believing the body. A 401 answers with a
  // problem document, and a cast is not a check — that is how this page once
  // reached `Object.entries(undefined)` and took itself down.
  if (!res.ok) throw new Error(res.status === 403 ? "Not permitted" : `HTTP ${res.status}`);
  // A 200 proves the request succeeded, NOT that the body has the shape this
  // cast claims — so every field read from it below is guarded. Written after
  // the first draft of this page crashed on `by_status.map` in exactly the way
  // DASH-001 crashed on `Object.entries`.
  return (await res.json()) as T;
}

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);
  const [daily, setDaily] = useState<Load<DailySummary>>({ state: "loading" });
  const [settlements, setSettlements] = useState<Load<SettlementSummary>>({ state: "loading" });
  const [readiness, setReadiness] = useState<Load<Readiness>>({ state: "loading" });
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  const signedIn = session?.authenticated === true;

  useEffect(() => {
    let cancelled = false;
    getSession()
      .then((s) => !cancelled && setSession(s))
      .catch(() => !cancelled && setSession({ authenticated: false }))
      .finally(() => !cancelled && setChecked(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    const today = new Date().toISOString().slice(0, 10);
    await Promise.all([
      getJson<DailySummary>(`/v1/reports/collection/daily?date_from=${today}&date_to=${today}`)
        .then((data) => setDaily({ state: "ready", data }))
        .catch((e: Error) => setDaily({ state: "error", message: e.message })),
      getJson<SettlementSummary>("/v1/reports/settlements")
        .then((data) => setSettlements({ state: "ready", data }))
        .catch((e: Error) => setSettlements({ state: "error", message: e.message })),
      getJson<Readiness>("/health/ready")
        .then((data) => setReadiness({ state: "ready", data }))
        .catch((e: Error) => setReadiness({ state: "error", message: e.message })),
    ]);
    setCheckedAt(new Date().toLocaleTimeString());
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    const initial = setTimeout(() => void load(), 0);
    return () => clearTimeout(initial);
  }, [load, signedIn]);

  if (!checked) {
    return (
      <div className="p-8">
        <LoadingState label="Checking your session…" />
      </div>
    );
  }

  if (!signedIn) {
    return (
      <div className="mx-auto w-full max-w-3xl p-8">
        <EmptyState
          title="Sign in to see today's collection"
          description="The dashboard reports on the organization you are signed in to."
          action={
            <a
              href="/login"
              className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              Sign in
            </a>
          }
        />
      </div>
    );
  }

  const currencies =
    daily.state === "ready" ? Object.entries(daily.data.payable_by_currency ?? {}) : [];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-6 lg:p-8">
      <PageHeader
        title="Dashboard"
        description="Today's collection across every centre in this organization, priced by the rate cards in force."
        actions={
          <Button type="button" variant="outline" onClick={() => void load()}>
            Refresh
          </Button>
        }
      />

      {daily.state === "error" ? (
        <ErrorState
          message={`Today's collection summary is unavailable — ${daily.message}.`}
          action={
            <Button type="button" size="sm" variant="outline" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      ) : null}

      <section aria-label="Today at a glance" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Collections today"
          value={daily.state === "ready" ? daily.data.transactions : "—"}
          hint={
            daily.state === "ready"
              ? `${daily.data.accepted} accepted · ${daily.data.rejected} rejected`
              : undefined
          }
          icon={<Activity className="size-4" />}
        />
        <StatTile
          label="Quantity today"
          value={
            daily.state === "ready" ? (
              <Quantity value={daily.data.total_net_weight_kg} unit="kg" />
            ) : (
              "—"
            )
          }
          hint={
            daily.state === "ready" && daily.data.weighted_avg_fat !== null
              ? `weighted average fat ${daily.data.weighted_avg_fat}%`
              : undefined
          }
          icon={<Droplets className="size-4" />}
        />
        <StatTile
          label="Value today"
          value={
            currencies.length > 0 ? (
              <Money amount={currencies[0][1]} currency={currencies[0][0]} />
            ) : daily.state === "ready" ? (
              <Money amount="0.00" currency="KES" />
            ) : (
              "—"
            )
          }
          hint={currencies.length > 1 ? `+ ${currencies.length - 1} more currency` : "payable"}
          icon={<Banknote className="size-4" />}
        />
        <StatTile
          label="Suppliers served"
          value={daily.state === "ready" ? daily.data.suppliers_served : "—"}
          hint={
            daily.state === "ready" && daily.data.in_progress
              ? `${daily.data.in_progress} still in progress`
              : "today"
          }
          icon={<Truck className="size-4" />}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Handshake aria-hidden className="size-4 text-muted-foreground" />
              Settlements
            </CardTitle>
          </CardHeader>
          <CardContent>
            {settlements.state === "loading" ? (
              <LoadingState label="Loading settlements…" />
            ) : settlements.state === "error" ? (
              <ErrorState message={`Unavailable — ${settlements.message}.`} />
            ) : !settlements.data.by_status?.length ? (
              <EmptyState
                title="No settlements yet"
                description="Settlements appear once a period is created and collected."
              />
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap gap-2">
                  {(settlements.data.by_status ?? []).map((row) => (
                    <span key={row.status} className="flex items-center gap-1.5">
                      <StatusBadge status={row.status} />
                      <span className="text-sm tabular-nums text-muted-foreground">
                        {row.count}
                      </span>
                    </span>
                  ))}
                </div>
                <dl className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Finalized net total</dt>
                    <dd className="mt-0.5">
                      <Money amount={settlements.data.finalized_net_total} emphasis />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Settlement lines</dt>
                    <dd className="mt-0.5 tabular-nums">{settlements.data.total_lines ?? 0}</dd>
                  </div>
                </dl>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users aria-hidden className="size-4 text-muted-foreground" />
              Platform health
            </CardTitle>
          </CardHeader>
          <CardContent>
            {readiness.state === "loading" ? (
              <LoadingState label="Checking the platform…" />
            ) : readiness.state === "error" ? (
              <ErrorState message={`The platform is unreachable — ${readiness.message}.`} />
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <StatusBadge status={readiness.data.platform_status ?? readiness.data.status} />
                  {checkedAt ? (
                    <span className="text-xs text-muted-foreground">checked {checkedAt}</span>
                  ) : null}
                </div>
                <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                  {Object.entries(readiness.data.checks ?? {}).map(([name, value]) => (
                    <li key={name} className="flex items-center justify-between gap-2">
                      <span className="text-muted-foreground">{name.replace(/_/g, " ")}</span>
                      <StatusBadge status={value} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
