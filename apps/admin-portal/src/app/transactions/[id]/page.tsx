"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Banknote,
  Building2,
  Check,
  Handshake,
  Receipt as ReceiptIcon,
  Truck,
} from "lucide-react";
import {
  ApiError,
  type CenterDetail,
  type CollectionChain,
  type Member,
  type MilkTransaction,
  type SupplierDetail,
  type TransactionEvent,
  type User,
  getCenterDetail,
  getCollectionChain,
  getMilkTransaction,
  getMilkTransactionEvents,
  getSupplierDetail,
  listPeople,
} from "@/lib/api";
import { formatStamp } from "@/components/datetime";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Money, Quantity, sameAmount } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { useLocale } from "@/lib/i18n";

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

/** One definition, shared with every other screen. */
const stamp = formatStamp;

/**
 * A one-line summary of an event's recorded data.
 *
 * Only the keys the domain actually writes, printed as they were stored. No
 * inference: if an event carried nothing, this returns nothing rather than
 * inventing a description of what probably happened.
 */
function summarise(data: Record<string, unknown> | null | undefined): string {
  if (!data) return "";
  const parts: string[] = [];
  for (const key of ["net", "gross", "tare", "fat", "snf", "clr", "method", "reason", "stage"]) {
    const value = (data as Record<string, unknown>)[key];
    if (value !== undefined && value !== null && value !== "") parts.push(`${key} ${value}`);
  }
  return parts.join(", ");
}

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
  // DEMO-007: a demo screen that says "centre 8f3c1a2b…" is a database
  // browser, not a product. Two keyed reads, once, give it names.
  const [center, setCenter] = useState<CenterDetail | null>(null);
  const [supplier, setSupplier] = useState<SupplierDetail | null>(null);
  const [people, setPeople] = useState<Array<Member & { user: User | null }>>([]);

  const load = useCallback(async () => {
    const ok =
      <T,>(set: (v: Load<T>) => void) =>
      (data: T) =>
        set({ state: "ready", data });
    const fail =
      <T,>(set: (v: Load<T>) => void) =>
      (e: unknown) =>
        set({ state: "error", message: describe(e) });

    const [loaded] = await Promise.allSettled([
      getMilkTransaction(id).then((data) => {
        ok(setTx)(data);
        return data;
      }, fail(setTx)),
      getMilkTransactionEvents(id).then(ok(setEvents), fail(setEvents)),
      getCollectionChain(id).then(ok(setChain), fail(setChain)),
    ]);

    // Names, not identifiers. Each is one keyed read and none of them may
    // break the page: a missing name degrades to the id, which is what the
    // page showed before.
    const transaction = loaded.status === "fulfilled" ? loaded.value : null;
    if (transaction) {
      getCenterDetail(transaction.center_id)
        .then(setCenter)
        .catch(() => setCenter(null));
      if (transaction.supplier_id) {
        getSupplierDetail(transaction.supplier_id)
          .then(setSupplier)
          .catch(() => setSupplier(null));
      }
    }
    listPeople()
      .then(setPeople)
      .catch(() => setPeople([]));
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
  // Optional at every hop: a name is a nicety, and a malformed or partial
  // response must degrade to the identifier rather than blank the page.
  const centerName = center?.center?.name ?? null;
  const supplierName = supplier?.profile?.full_name ?? supplier?.supplier?.full_name ?? null;
  const actorName: Record<string, string> = {};
  for (const person of people) {
    if (person.user?.full_name) actorName[person.user_id] = person.user.full_name;
    else if (person.user?.email) actorName[person.user_id] = person.user.email;
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[
          { label: "Collections", href: "/transactions" },
          { label: t ? t.id.slice(0, 8) : "Collection" },
        ]}
        title="Collection"
        description={
          t
            ? [
                `${t.id.slice(0, 8)}…`,
                stamp(t.created_at),
                centerName ?? null,
                supplierName ?? null,
              ]
                .filter(Boolean)
                .join(" · ")
            : "Loading this collection…"
        }
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
                  <Row label="Weight source">
                    <SourceTag source={t.weight_source} />
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
                        {supplierName ?? `${t.supplier_id.slice(0, 8)}…`}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">not identified</span>
                    )}
                  </Row>
                  <Row label="Centre">
                    <Link className="hover:underline" href={`/centers/${t.center_id}`}>
                      <Building2 aria-hidden className="mr-1 inline size-3.5" />
                      {centerName ?? `${t.center_id.slice(0, 8)}…`}
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
                  <Row label="Quality source">
                    <SourceTag source={t.quality_source} />
                  </Row>
                  {t.quality_remarks ? (
                    <Row label="Remarks">
                      <span className="text-right text-muted-foreground">{t.quality_remarks}</span>
                    </Row>
                  ) : null}
                  <Row label="Pricing status">
                    <StatusBadge status={t.pricing_status ?? "unpriced"} />
                  </Row>
                  {t.decided_at ? (
                    <Row label="Decided">
                      <span className="text-right text-muted-foreground">
                        {stamp(t.decided_at)}
                        {t.decided_by && actorName[t.decided_by]
                          ? ` · ${actorName[t.decided_by]}`
                          : ""}
                      </span>
                    </Row>
                  ) : null}
                  {t.rejected_reason ? (
                    <Row label="Rejected">
                      <span className="text-destructive">{t.rejected_reason}</span>
                    </Row>
                  ) : null}
                  {t.cancelled_reason ? (
                    <Row label="Cancelled">
                      <span className="text-destructive">{t.cancelled_reason}</span>
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

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Money trail</CardTitle>
                <CardDescription>
                  What this collection was worth, and what happened to it. Every figure is the
                  platform&apos;s; the only thing computed here is whether two of them agree.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <MoneyTrail tx={t} chain={chain} />
              </CardContent>
            </Card>

            <Timeline events={events} chain={chain} actorName={actorName} />
          </div>
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
/**
 * How a reading was obtained.
 *
 * DEMO-005 built the capture wizard on the rule that the UI must never pretend
 * a hardware device supplied a value when it did not; the platform has stored
 * `weight_source` and `quality_source` since MVP-001 to make that checkable.
 * This is where the stored answer finally shows up. "manual" is the domain's
 * own word for an operator typing it in — it is not a failure, and it is not
 * something to hide.
 */
function SourceTag({ source }: { source: string | null }) {
  if (!source) return <span className="text-muted-foreground">—</span>;
  const manual = source === "manual";
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={manual ? "text-muted-foreground" : ""}>
        {source.replace(/_/g, " ")}
      </span>
      {manual ? (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
          entered by an operator
        </span>
      ) : null}
    </span>
  );
}

/**
 * The money, followed from this collection to the receipt (DEMO-007 §6).
 *
 * Every figure is a string the platform stored, printed. The portal does not
 * multiply, does not sum and does not subtract — with ONE exception, which is
 * the point of the panel: the difference between what this collection was
 * worth and what the settlement recorded for it. That subtraction exists to
 * be shown, and it is expected to be 0.00. If it ever is not, this is the
 * screen that says so instead of the screen that hides it.
 */
function MoneyTrail({ tx, chain }: { tx: MilkTransaction; chain: Load<CollectionChain> }) {
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const { currency: orgCurrency } = useLocale();

  if (chain.state === "loading") return <LoadingState label="Following the money…" />;
  if (chain.state === "error")
    return <ErrorState message={`The financial trail is unavailable — ${chain.message}.`} />;

  const links = chain.data;
  const currency = tx.currency ?? links.settlement?.currency ?? orgCurrency;
  const collected = tx.gross_amount == null ? null : String(tx.gross_amount);
  const contributed = links.settlement ? String(links.settlement.line_amount) : null;

  // COMPARED, not computed. `sameAmount` normalises two exact-decimal strings
  // and asks whether they denote the same amount — "450.00" and "450.0" do.
  // Subtracting them in JavaScript would be float arithmetic on money, which
  // is the one thing this portal never does.
  const comparable = collected != null && contributed != null;
  const agrees = comparable && sameAmount(collected, contributed);

  const stages: { label: string; amount: string | null; note: string; href?: string }[] = [
    {
      label: "Collection",
      amount: collected,
      // Deliberately NOT the rate card string: the pricing card above already
      // prints it, and the same identifier twice on one screen reads as two
      // facts.
      note: "what this delivery was worth when it was priced",
    },
    {
      label: "Settlement contribution",
      amount: contributed,
      note: links.settlement
        ? `${links.settlement.settlement_number} · ${links.settlement.status}`
        : "not settled yet",
      href: links.settlement ? `/settlements/${links.settlement.id}` : undefined,
    },
    {
      label: "Payment allocation",
      amount: links.payment ? String(links.payment.allocated_amount) : null,
      note: links.payment
        ? `${links.payment.payment_number} · ${links.payment.status}`
        : "not paid yet",
      href: links.payment ? `/payments/${links.payment.id}` : undefined,
    },
    {
      label: "Receipt",
      amount: links.receipt ? String(links.receipt.net_amount) : null,
      note: links.receipt
        ? `${links.receipt.receipt_number} · covers the whole payment`
        : "no receipt yet",
      href: links.payment ? `/payments/${links.payment.id}` : undefined,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <ol className="flex flex-col divide-y">
        {stages.map((stage) => (
          <li key={stage.label} className="flex items-baseline justify-between gap-4 py-3">
            <div className="flex flex-col">
              {stage.href ? (
                <Link className="text-sm font-medium hover:underline" href={stage.href}>
                  {stage.label}
                </Link>
              ) : (
                <span className="text-sm font-medium">{stage.label}</span>
              )}
              <span className="text-xs text-muted-foreground">{stage.note}</span>
            </div>
            {stage.amount != null ? (
              <Money amount={stage.amount} currency={currency} />
            ) : (
              <span className="text-sm text-muted-foreground">—</span>
            )}
          </li>
        ))}
      </ol>

      {comparable ? (
        agrees ? (
          <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Check aria-hidden className="size-4" />
            The settlement recorded this collection at exactly its collection value — difference
            0.00 {currency}.
          </p>
        ) : (
          <p
            role="alert"
            className="inline-flex items-center gap-2 text-sm font-medium text-destructive"
          >
            <AlertTriangle aria-hidden className="size-4" />
            The settlement recorded {contributed} {currency} for a collection worth {collected}{" "}
            {currency}. These should be identical.
          </p>
        )
      ) : null}
    </div>
  );
}

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
  actorName,
}: {
  events: Load<TransactionEvent[]>;
  chain: Load<CollectionChain>;
  /** user id → display name, resolved once from the staff roster. */
  actorName: Record<string, string>;
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
                <span className="flex flex-1 flex-col gap-0.5">
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{humanise(event.event_type)}</span>
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {stamp(event.created_at)}
                    </span>
                  </span>
                  {/* Who did it, where the platform recorded an actor. An
                      unattributed event says so rather than guessing. */}
                  <span className="text-xs text-muted-foreground">
                    {event.actor_id
                      ? (actorName[event.actor_id] ?? `operator ${event.actor_id.slice(0, 8)}…`)
                      : "the platform"}
                    {summarise(event.data) ? ` · ${summarise(event.data)}` : ""}
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
