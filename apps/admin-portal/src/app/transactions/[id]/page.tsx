"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Banknote, Building2, Check, Handshake, Receipt as ReceiptIcon, Truck } from "lucide-react";
import {
  ApiError,
  type CollectionChain,
  type MilkTransaction,
  type TransactionEvent,
  getCollectionChain,
  getMilkTransaction,
  getMilkTransactionEvents,
} from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * One collection, end to end (DEMO-004).
 *
 * The strongest screen in the demonstration, and the one with the most ways to
 * lie. Two rules hold it honest:
 *
 * 1. THE PRICING BREAKDOWN IS NOT RECOMPUTED. `quantity × rate` is displayed as
 *    an EXPRESSION — the operands and the result are three separate strings the
 *    platform sent, printed side by side. The portal never evaluates it. If the
 *    engine and the display ever disagreed, this page would show the
 *    disagreement rather than hide it behind a browser's arithmetic.
 *
 * 2. THE TIMELINE IS THE REAL EVENT LOG. Collection stages come from
 *    `/events`, the platform's own trail; settlement, payment and receipt come
 *    from the chain aggregate. A stage that has not happened is shown as not
 *    happened — never inferred, never filled in.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;
const describe = (e: unknown) =>
  e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "the request failed";

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 19).replace("T", " ") : "—";

/** `TransactionCreated` → `Transaction created` — sentence case, not Title Case. */
const humanise = (event: string) =>
  event
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_.]/g, " ")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());

export default function TransactionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [tx, setTx] = useState<Load<MilkTransaction>>(LOADING);
  const [events, setEvents] = useState<Load<TransactionEvent[]>>(LOADING);
  const [chain, setChain] = useState<Load<CollectionChain>>(LOADING);

  const load = useCallback(async () => {
    const ok =
      <T,>(set: (v: Load<T>) => void) =>
      (data: T) =>
        set({ state: "ready", data });
    const fail =
      <T,>(set: (v: Load<T>) => void) =>
      (e: unknown) =>
        set({ state: "error", message: describe(e) });

    await Promise.allSettled([
      getMilkTransaction(id).then(ok(setTx), fail(setTx)),
      getMilkTransactionEvents(id).then(ok(setEvents), fail(setEvents)),
      getCollectionChain(id).then(ok(setChain), fail(setChain)),
    ]);
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  if (tx.state === "error") {
    return (
      <div className="mx-auto w-full max-w-3xl p-8">
        <ErrorState message={`This collection could not be loaded — ${tx.message}.`} />
        <p className="mt-4 text-sm">
          <Link className="underline underline-offset-4" href="/transactions">
            Back to collections
          </Link>
        </p>
      </div>
    );
  }

  const t = tx.state === "ready" ? tx.data : null;
  const links = chain.state === "ready" ? chain.data : null;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[
          { label: "Collections", href: "/transactions" },
          { label: t ? t.id.slice(0, 8) : "Collection" },
        ]}
        title="Collection"
        description={t ? `${t.id} · recorded ${stamp(t.created_at)}` : "Loading this collection…"}
        actions={t ? <StatusBadge status={t.state} /> : undefined}
      />

      {tx.state === "loading" ? <LoadingState label="Loading the collection…" /> : null}

      {t ? (
        <>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Collection</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="flex flex-col gap-2.5 text-sm">
                  <Row label="Quantity">
                    <Quantity value={t.net_weight} unit={t.weight_unit ?? "kg"} />
                  </Row>
                  <Row label="Gross / tare">
                    <span className="tabular-nums text-muted-foreground">
                      {t.gross_weight ?? "—"} / {t.tare_weight ?? "—"}
                    </span>
                  </Row>
                  <Row label="Milk">
                    <span className="text-muted-foreground">{t.milk_type ?? "—"}</span>
                  </Row>
                  <Row label="Container">
                    <span className="text-muted-foreground">
                      {t.container_type ?? "—"} {t.container_identifier ?? ""}
                    </span>
                  </Row>
                  <Row label="Supplier">
                    {t.supplier_id ? (
                      <Link className="hover:underline" href={`/suppliers/${t.supplier_id}`}>
                        <Truck aria-hidden className="mr-1 inline size-3.5" />
                        {t.supplier_id.slice(0, 8)}…
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">not identified</span>
                    )}
                  </Row>
                  <Row label="Centre">
                    <Link className="hover:underline" href={`/centers/${t.center_id}`}>
                      <Building2 aria-hidden className="mr-1 inline size-3.5" />
                      {t.center_id.slice(0, 8)}…
                    </Link>
                  </Row>
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Quality</CardTitle>
                <CardDescription>The readings the price was resolved from.</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="flex flex-col gap-2.5 text-sm">
                  <Row label="Fat">
                    <span className="tabular-nums">{t.fat ?? "—"}%</span>
                  </Row>
                  <Row label="SNF">
                    <span className="tabular-nums">{t.snf ?? "—"}</span>
                  </Row>
                  <Row label="CLR">
                    <span className="tabular-nums">{t.clr ?? "—"}</span>
                  </Row>
                  <Row label="Pricing status">
                    <StatusBadge status={t.pricing_status ?? "unpriced"} />
                  </Row>
                  {t.rejected_reason ? (
                    <Row label="Rejected">
                      <span className="text-destructive">{t.rejected_reason}</span>
                    </Row>
                  ) : null}
                </dl>
              </CardContent>
            </Card>

            <PricingBreakdown tx={t} />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <ChainCard
              title="Settlement"
              icon={<Handshake aria-hidden className="size-4 text-muted-foreground" />}
              state={chain}
              empty="This collection has not been settled yet."
              href={links?.settlement ? `/settlements/${links.settlement.id}` : undefined}
              rows={
                links?.settlement
                  ? [
                      ["Number", links.settlement.settlement_number],
                      ["Status", <StatusBadge key="s" status={links.settlement.status} />],
                      [
                        "Period",
                        `${links.settlement.period_from} → ${links.settlement.period_to}`,
                      ],
                      [
                        "This collection",
                        <Money
                          key="l"
                          amount={links.settlement.line_amount}
                          currency={links.settlement.currency}
                        />,
                      ],
                      [
                        "Settlement net",
                        <Money
                          key="n"
                          amount={links.settlement.net_amount}
                          currency={links.settlement.currency}
                          emphasis
                        />,
                      ],
                      ["Finalized", stamp(links.settlement.finalized_at)],
                    ]
                  : null
              }
            />

            <ChainCard
              title="Payment"
              icon={<Banknote aria-hidden className="size-4 text-muted-foreground" />}
              state={chain}
              empty={
                links?.settlement
                  ? "The settlement has not been paid yet."
                  : "Payment follows settlement."
              }
              href={links?.payment ? `/payments/${links.payment.id}` : undefined}
              rows={
                links?.payment
                  ? [
                      ["Number", links.payment.payment_number],
                      ["Status", <StatusBadge key="s" status={links.payment.status} />],
                      ["Method", links.payment.method.replace(/_/g, " ").toLowerCase()],
                      ["Reference", links.payment.reference ?? "—"],
                      [
                        "Allocated",
                        <Money
                          key="a"
                          amount={links.payment.allocated_amount}
                          currency={links.payment.currency}
                        />,
                      ],
                      ["Paid", stamp(links.payment.paid_at)],
                    ]
                  : null
              }
            />

            <ChainCard
              title="Receipt"
              icon={<ReceiptIcon aria-hidden className="size-4 text-muted-foreground" />}
              state={chain}
              empty={
                links?.payment
                  ? "A receipt is generated once the payment completes."
                  : "A receipt follows payment."
              }
              href={links?.receipt && links.payment ? `/payments/${links.payment.id}` : undefined}
              linkLabel="open on payment"
              rows={
                links?.receipt
                  ? [
                      ["Number", links.receipt.receipt_number],
                      ["Status", <StatusBadge key="s" status={links.receipt.status} />],
                      [
                        "Amount",
                        <Money
                          key="n"
                          amount={links.receipt.net_amount}
                          currency={links.receipt.currency}
                          emphasis
                        />,
                      ],
                      ["Generated", stamp(links.receipt.generated_at)],
                    ]
                  : null
              }
            />
          </div>

          <Timeline events={events} chain={chain} />
        </>
      ) : null}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

/**
 * The pricing breakdown.
 *
 * The expression is PRINTED, not evaluated: `net_weight`, `unit_price` and
 * `gross_amount` are three values the platform computed, shown together so an
 * operator can check the arithmetic themselves. The portal deliberately does
 * not multiply them — that would be a second pricing engine, and a second
 * engine is a second answer.
 */
function PricingBreakdown({ tx }: { tx: MilkTransaction }) {
  const priced = tx.unit_price != null && tx.gross_amount != null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Pricing</CardTitle>
        <CardDescription>Resolved by the platform&apos;s pricing engine.</CardDescription>
      </CardHeader>
      <CardContent>
        {!priced ? (
          <EmptyState
            title="Not priced"
            description="A price is resolved once quality has been captured."
          />
        ) : (
          <div className="flex flex-col gap-4">
            <dl className="flex flex-col gap-2.5 text-sm">
              <Row label="Rate card">
                <span className="text-right text-muted-foreground">
                  {tx.pricing_detail ?? "—"}
                </span>
              </Row>
              <Row label="Quantity">
                <Quantity value={tx.net_weight} unit={tx.weight_unit ?? "kg"} />
              </Row>
              <Row label="Rate">
                <span className="tabular-nums">
                  {String(tx.unit_price)}
                  <span className="ml-1 text-xs text-muted-foreground">
                    {tx.currency}/{tx.weight_unit ?? "kg"}
                  </span>
                </span>
              </Row>
            </dl>

            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                Calculation
              </p>
              <p className="font-mono text-sm tabular-nums">
                {String(tx.net_weight)} × {String(tx.unit_price)}
              </p>
              <p className="mt-1 font-mono text-sm tabular-nums">
                = {String(tx.gross_amount)} {tx.currency}
              </p>
            </div>

            <div className="flex items-baseline justify-between border-t border-border pt-3">
              <span className="text-sm text-muted-foreground">Collection value</span>
              <Money amount={tx.gross_amount} currency={tx.currency} emphasis />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ChainCard({
  title,
  icon,
  state,
  rows,
  empty,
  href,
  linkLabel = "open",
}: {
  title: string;
  icon: React.ReactNode;
  state: Load<CollectionChain>;
  rows: [string, React.ReactNode][] | null;
  empty: string;
  href?: string;
  // DEMO-006: these cards used to point at list pages because no detail page
  // existed. They now open the exact record.
  linkLabel?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        {href ? (
          <Link className="text-xs underline-offset-4 hover:underline" href={href}>
            {linkLabel}
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        {state.state === "loading" ? (
          <LoadingState label={`Loading ${title.toLowerCase()}…`} />
        ) : state.state === "error" ? (
          <ErrorState message={`Unavailable — ${state.message}.`} />
        ) : rows === null ? (
          <p className="py-4 text-sm text-muted-foreground">{empty}</p>
        ) : (
          <dl className="flex flex-col gap-2.5 text-sm">
            {rows.map(([label, value]) => (
              <Row key={label} label={label}>
                {value}
              </Row>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * The lifecycle, from the platform's own records.
 *
 * Collection stages are the real event log. The three money stages come from
 * the chain aggregate and appear only once they have actually happened — a
 * pending stage is drawn as pending, never as done.
 */
function Timeline({
  events,
  chain,
}: {
  events: Load<TransactionEvent[]>;
  chain: Load<CollectionChain>;
}) {
  const links = chain.state === "ready" ? chain.data : null;
  const recorded = events.state === "ready" ? (events.data ?? []) : [];

  const later: { label: string; at: string | null; done: boolean }[] = [
    {
      label: links?.settlement
        ? `Included in settlement ${links.settlement.settlement_number}`
        : "Included in a settlement",
      at: null,
      done: Boolean(links?.settlement),
    },
    {
      label: links?.settlement
        ? `Settlement ${links.settlement.status}`
        : "Settlement finalized",
      at: links?.settlement?.finalized_at ?? null,
      done: links?.settlement?.status === "finalized",
    },
    {
      label: links?.payment
        ? `Payment ${links.payment.payment_number} ${links.payment.status}`
        : "Payment processed",
      at: links?.payment?.paid_at ?? null,
      done: links?.payment?.status === "completed",
    },
    {
      label: links?.receipt ? `Receipt ${links.receipt.receipt_number}` : "Receipt generated",
      at: links?.receipt?.generated_at ?? null,
      done: Boolean(links?.receipt),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Lifecycle</CardTitle>
        <CardDescription>
          The platform&apos;s own event trail. Stages that have not happened are shown as pending.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {events.state === "loading" ? (
          <LoadingState label="Loading the trail…" />
        ) : events.state === "error" ? (
          <ErrorState message={`The event trail is unavailable — ${events.message}.`} />
        ) : recorded.length === 0 ? (
          <EmptyState title="No events recorded for this collection" />
        ) : (
          <ol className="flex flex-col">
            {recorded.map((event) => (
              <li key={`${event.sequence}-${event.event_type}`} className="flex gap-3 pb-4 last:pb-0">
                <span className="relative flex flex-col items-center">
                  <span className="mt-1 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15">
                    <Check aria-hidden className="size-3 text-primary" />
                  </span>
                  <span className="mt-1 w-px flex-1 bg-border" />
                </span>
                <span className="flex flex-1 flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{humanise(event.event_type)}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {stamp(event.created_at)}
                  </span>
                </span>
              </li>
            ))}

            {later.map((stage) => (
              <li key={stage.label} className="flex gap-3 pb-4 last:pb-0">
                <span className="relative flex flex-col items-center">
                  <span
                    className={
                      stage.done
                        ? "mt-1 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15"
                        : "mt-1 flex size-5 shrink-0 items-center justify-center rounded-full border border-dashed border-border"
                    }
                  >
                    {stage.done ? <Check aria-hidden className="size-3 text-primary" /> : null}
                  </span>
                  <span className="mt-1 w-px flex-1 bg-border" />
                </span>
                <span className="flex flex-1 flex-wrap items-baseline justify-between gap-2">
                  <span
                    className={
                      stage.done ? "text-sm font-medium" : "text-sm text-muted-foreground"
                    }
                  >
                    {stage.label}
                  </span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {stage.done ? stamp(stage.at) : "pending"}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
