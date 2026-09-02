"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Banknote,
  Building2,
  Check,
  Copy,
  Handshake,
  Printer,
  Receipt as ReceiptIcon,
  Truck,
} from "lucide-react";
import {
  type CenterDetail,
  type CollectionChain,
  type CollectionSlip,
  type Member,
  type MilkTransaction,
  repriceTransaction,
  type SupplierDetail,
  type TransactionEvent,
  type User,
  getCenterDetail,
  getCollectionChain,
  getCollectionSlip,
  getMilkTransaction,
  getMilkTransactionEvents,
  getSupplierDetail,
  listPeople,
  describeError,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatStamp } from "@/components/datetime";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Money, Quantity, sameAmount } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { useLocale, useT } from "@/lib/i18n";

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
const describe = (e: unknown, fallback: string) =>
  describeError(e, e instanceof Error ? e.message : fallback);

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
  for (const key of [
    "net",
    "gross",
    "tare",
    "fat",
    "snf",
    "clr",
    "method",
    "reason",
    "stage",
  ]) {
    const value = (data as Record<string, unknown>)[key];
    if (value !== undefined && value !== null && value !== "")
      parts.push(`${key} ${value}`);
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

export default function TransactionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t9n = useT();
  const [tx, setTx] = useState<Load<MilkTransaction>>(LOADING);
  const [events, setEvents] = useState<Load<TransactionEvent[]>>(LOADING);
  const [chain, setChain] = useState<Load<CollectionChain>>(LOADING);
  // DEMO-007: a demo screen that says "centre 8f3c1a2b…" is a database
  // browser, not a product. Two keyed reads, once, give it names.
  const [center, setCenter] = useState<CenterDetail | null>(null);
  const [supplier, setSupplier] = useState<SupplierDetail | null>(null);
  const [people, setPeople] = useState<Array<Member & { user: User | null }>>(
    [],
  );
  // LACTEVA-BACKEND-001: resolving a price the platform could not compute at
  // capture. Local to this card — the rest of the page is a read.
  const [repricing, setRepricing] = useState(false);
  const [repriceError, setRepriceError] = useState<string | null>(null);

  /** Ask the platform to price it now that a card may cover it. */
  async function resolvePrice() {
    setRepricing(true);
    setRepriceError(null);
    try {
      const priced = await repriceTransaction(id);
      setTx({ state: "ready", data: priced });
    } catch (e) {
      // The platform's own reason — "no published rate card covers this
      // center, product, and date" is the sentence that tells an
      // administrator what to go and do. The badge stays Rate pending.
      setRepriceError(describeError(e, t9n("txDetail.requestFailed")));
    } finally {
      setRepricing(false);
    }
  }

  const load = useCallback(async () => {
    const ok =
      <T,>(set: (v: Load<T>) => void) =>
      (data: T) =>
        set({ state: "ready", data });
    const fail =
      <T,>(set: (v: Load<T>) => void) =>
      (e: unknown) =>
        set({
          state: "error",
          message: describe(e, t9n("txDetail.requestFailed")),
        });

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
  }, [id, t9n]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  if (tx.state === "error") {
    return (
      <PageContainer width="narrow">
        <ErrorState
          message={t9n("txDetail.loadFailed", { message: tx.message })}
        />
        <p className="mt-4 text-sm">
          <Link className="underline underline-offset-4" href="/transactions">
            {t9n("txDetail.backToCollections")}
          </Link>
        </p>
      </PageContainer>
    );
  }

  const t = tx.state === "ready" ? tx.data : null;
  const links = chain.state === "ready" ? chain.data : null;
  // Optional at every hop: a name is a nicety, and a malformed or partial
  // response must degrade to the identifier rather than blank the page.
  const centerName = center?.center?.name ?? null;
  const supplierName =
    supplier?.profile?.full_name ?? supplier?.supplier?.full_name ?? null;
  const actorName: Record<string, string> = {};
  for (const person of people) {
    if (person.user?.full_name)
      actorName[person.user_id] = person.user.full_name;
    else if (person.user?.email) actorName[person.user_id] = person.user.email;
  }

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[
          { label: t9n("dashboard.collections"), href: "/transactions" },
          { label: t ? t.id.slice(0, 8) : t9n("txDetail.collection") },
        ]}
        title={t9n("txDetail.collection")}
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
            : t9n("txDetail.loadingThis")
        }
        actions={t ? <StatusBadge status={t.state} /> : undefined}
      />

      {tx.state === "loading" ? (
        <LoadingState label={t9n("txDetail.loadingCollection")} />
      ) : null}

      {t ? (
        <>
          <div className="grid gap-6 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t9n("txDetail.collection")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="flex flex-col gap-2.5 text-sm">
                  <Row label={t9n("field.quantity")}>
                    <Quantity
                      value={t.net_weight}
                      unit={t.weight_unit ?? "kg"}
                    />
                  </Row>
                  <Row label={t9n("txDetail.grossTare")}>
                    <span className="tabular-nums text-muted-foreground">
                      {t.gross_weight ?? "—"} / {t.tare_weight ?? "—"}
                    </span>
                  </Row>
                  <Row label={t9n("txDetail.weightSource")}>
                    <SourceTag source={t.weight_source} />
                  </Row>
                  <Row label={t9n("txDetail.milk")}>
                    <span className="text-muted-foreground">
                      {t.milk_type ?? "—"}
                    </span>
                  </Row>
                  <Row label={t9n("txDetail.container")}>
                    <span className="text-muted-foreground">
                      {t.container_type ?? "—"} {t.container_identifier ?? ""}
                    </span>
                  </Row>
                  <Row label={t9n("entity.supplier")}>
                    {t.supplier_id ? (
                      <Link
                        className="hover:underline"
                        href={`/suppliers/${t.supplier_id}`}
                      >
                        <Truck aria-hidden className="me-1 inline size-3.5" />
                        {supplierName ?? `${t.supplier_id.slice(0, 8)}…`}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">
                        {t9n("tx.notIdentified")}
                      </span>
                    )}
                  </Row>
                  <Row label={t9n("tx.centre")}>
                    <Link
                      className="hover:underline"
                      href={`/centers/${t.center_id}`}
                    >
                      <Building2 aria-hidden className="me-1 inline size-3.5" />
                      {centerName ?? `${t.center_id.slice(0, 8)}…`}
                    </Link>
                  </Row>
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t9n("transaction.quality")}
                </CardTitle>
                <CardDescription>{t9n("txDetail.qualityHint")}</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="flex flex-col gap-2.5 text-sm">
                  <Row label={t9n("txDetail.fat")}>
                    <span className="tabular-nums">{t.fat ?? "—"}%</span>
                  </Row>
                  <Row label="SNF">
                    <span className="tabular-nums">{t.snf ?? "—"}</span>
                  </Row>
                  <Row label="CLR">
                    <span className="tabular-nums">{t.clr ?? "—"}</span>
                  </Row>
                  <Row label={t9n("txDetail.qualitySource")}>
                    <SourceTag source={t.quality_source} />
                  </Row>
                  {t.quality_remarks ? (
                    <Row label={t9n("txDetail.remarks")}>
                      <span className="text-end text-muted-foreground">
                        {t.quality_remarks}
                      </span>
                    </Row>
                  ) : null}
                  <Row label={t9n("txDetail.pricingStatus")}>
                    <StatusBadge status={t.pricing_status ?? "unpriced"} />
                  </Row>
                  {t.pricing_status === "pricing_unavailable" ? (
                    <div className="flex flex-col gap-2 py-2">
                      <p className="text-xs text-muted-foreground">
                        {t9n("txDetail.ratePendingHelp")}
                      </p>
                      {repriceError ? (
                        <p className="text-xs text-destructive" role="alert">
                          {repriceError}
                        </p>
                      ) : null}
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="self-start"
                        disabled={repricing}
                        onClick={() => void resolvePrice()}
                      >
                        {repricing
                          ? t9n("txDetail.resolving")
                          : t9n("txDetail.resolvePrice")}
                      </Button>
                    </div>
                  ) : null}
                  {t.decided_at ? (
                    <Row label={t9n("txDetail.decided")}>
                      <span className="text-end text-muted-foreground">
                        {stamp(t.decided_at)}
                        {t.decided_by && actorName[t.decided_by]
                          ? ` · ${actorName[t.decided_by]}`
                          : ""}
                      </span>
                    </Row>
                  ) : null}
                  {t.rejected_reason ? (
                    <Row label={t9n("transaction.rejected")}>
                      <span className="text-destructive">
                        {t.rejected_reason}
                      </span>
                    </Row>
                  ) : null}
                  {t.cancelled_reason ? (
                    <Row label={t9n("billing.cancelled")}>
                      <span className="text-destructive">
                        {t.cancelled_reason}
                      </span>
                    </Row>
                  ) : null}
                </dl>
              </CardContent>
            </Card>

            <PricingBreakdown tx={t} />
          </div>

          {t.state === "COMPLETED" ? <SlipCard txId={t.id} /> : null}

          <div className="grid gap-6 lg:grid-cols-3">
            <ChainCard
              title={t9n("entity.settlement")}
              icon={
                <Handshake
                  aria-hidden
                  className="size-4 text-muted-foreground"
                />
              }
              state={chain}
              empty={t9n("txDetail.notSettledYet")}
              href={
                links?.settlement
                  ? `/settlements/${links.settlement.id}`
                  : undefined
              }
              rows={
                links?.settlement
                  ? [
                      [
                        t9n("txDetail.number"),
                        links.settlement.settlement_number,
                      ],
                      [
                        t9n("field.status"),
                        <StatusBadge
                          key="s"
                          status={links.settlement.status}
                        />,
                      ],
                      [
                        t9n("field.period"),
                        `${links.settlement.period_from} → ${links.settlement.period_to}`,
                      ],
                      [
                        t9n("txDetail.thisCollection"),
                        <Money
                          key="l"
                          amount={links.settlement.line_amount}
                          currency={links.settlement.currency}
                        />,
                      ],
                      [
                        t9n("txDetail.settlementNet"),
                        <Money
                          key="n"
                          amount={links.settlement.net_amount}
                          currency={links.settlement.currency}
                          emphasis
                        />,
                      ],
                      [
                        t9n("settlement.finalized"),
                        stamp(links.settlement.finalized_at),
                      ],
                    ]
                  : null
              }
            />

            <ChainCard
              title={t9n("entity.payment")}
              icon={
                <Banknote
                  aria-hidden
                  className="size-4 text-muted-foreground"
                />
              }
              state={chain}
              empty={
                links?.settlement
                  ? t9n("txDetail.settlementNotPaid")
                  : t9n("txDetail.paymentFollows")
              }
              href={
                links?.payment ? `/payments/${links.payment.id}` : undefined
              }
              rows={
                links?.payment
                  ? [
                      [t9n("txDetail.number"), links.payment.payment_number],
                      [
                        t9n("field.status"),
                        <StatusBadge key="s" status={links.payment.status} />,
                      ],
                      [
                        t9n("payment.method"),
                        links.payment.method.replace(/_/g, " ").toLowerCase(),
                      ],
                      [
                        t9n("payment.reference"),
                        links.payment.reference ?? "—",
                      ],
                      [
                        t9n("txDetail.allocated"),
                        <Money
                          key="a"
                          amount={links.payment.allocated_amount}
                          currency={links.payment.currency}
                        />,
                      ],
                      [t9n("field.paid"), stamp(links.payment.paid_at)],
                    ]
                  : null
              }
            />

            <ChainCard
              title={t9n("entity.receipt")}
              icon={
                <ReceiptIcon
                  aria-hidden
                  className="size-4 text-muted-foreground"
                />
              }
              state={chain}
              empty={
                links?.payment
                  ? t9n("txDetail.receiptWhenPaid")
                  : t9n("txDetail.receiptFollows")
              }
              href={
                links?.receipt && links.payment
                  ? `/payments/${links.payment.id}`
                  : undefined
              }
              linkLabel={t9n("txDetail.openOnPayment")}
              rows={
                links?.receipt
                  ? [
                      [t9n("txDetail.number"), links.receipt.receipt_number],
                      [
                        t9n("field.status"),
                        <StatusBadge key="s" status={links.receipt.status} />,
                      ],
                      [
                        t9n("field.amount"),
                        <Money
                          key="n"
                          amount={links.receipt.net_amount}
                          currency={links.receipt.currency}
                          emphasis
                        />,
                      ],
                      [
                        t9n("receipt.generated"),
                        stamp(links.receipt.generated_at),
                      ],
                    ]
                  : null
              }
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t9n("txDetail.moneyTrail")}
                </CardTitle>
                <CardDescription>
                  {t9n("txDetail.moneyTrailHint")}
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
    </PageContainer>
  );
}

/**
 * The collection slip / parchi (P0-BIZ-003).
 *
 * The farmer's copy of this collection, composed entirely by the platform:
 * the portal prints the fields it was sent and never recomputes a figure.
 * Print produces only the slip (see the `[data-slip-print]` rules in
 * globals.css); Copy carries the platform's shareable text — bilingual when
 * the organization's language is Hindi — for WhatsApp or SMS.
 */
function SlipCard({ txId }: { txId: string }) {
  const t9n = useT();
  const [slip, setSlip] = useState<Load<CollectionSlip>>(LOADING);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    getCollectionSlip(txId).then(
      (data) => {
        if (live) setSlip({ state: "ready", data });
      },
      (e: unknown) => {
        if (live)
          setSlip({
            state: "error",
            message: describe(e, t9n("txDetail.requestFailed")),
          });
      },
    );
    return () => {
      live = false;
    };
  }, [txId, t9n]);

  if (slip.state === "loading") {
    return <LoadingState label={t9n("txDetail.slipPreparing")} />;
  }
  if (slip.state === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t9n("txDetail.slipTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorState
            message={t9n("txDetail.slipFailed", { message: slip.message })}
          />
        </CardContent>
      </Card>
    );
  }

  const s = slip.data;
  const milk = s.milk_type_custom ?? s.milk_type ?? "—";
  const farmer =
    [s.supplier_code, s.supplier_name].filter(Boolean).join(" · ") || "—";
  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(s.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (permissions, http); the text stays
      // selectable on screen, so failing silently loses nothing.
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {t9n("txDetail.slipTitle")} ·{" "}
          <span className="tabular-nums">{s.slip_number}</span>
        </CardTitle>
        <CardDescription>{t9n("txDetail.slipHint")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          data-slip-print
          className="mx-auto w-full max-w-sm rounded-md border bg-card p-4 text-sm"
        >
          <p className="text-center font-semibold">{s.organization_name}</p>
          <p className="text-center text-muted-foreground">
            {s.center_name}
            {s.session_label ? ` · ${s.session_label}` : ""}
          </p>
          <dl className="mt-3 flex flex-col gap-1.5">
            <Row label={t9n("txDetail.slipLabel")}>
              <span className="tabular-nums">{s.slip_number}</span>
            </Row>
            <Row label={t9n("field.date")}>
              <span className="tabular-nums">{stamp(s.collected_at)}</span>
            </Row>
            <Row label={t9n("txDetail.farmer")}>{farmer}</Row>
            <Row label={t9n("txDetail.milk")}>{milk}</Row>
            <Row label={t9n("field.quantity")}>
              <Quantity value={s.quantity} unit={s.weight_unit ?? "kg"} />
            </Row>
            <Row label="FAT / SNF / CLR">
              <span className="tabular-nums">
                {s.fat ?? "—"} / {s.snf ?? "—"} / {s.clr ?? "—"}
              </span>
            </Row>
            {s.decision === "REJECTED" ? (
              <Row label={t9n("txDetail.decision")}>
                <span className="text-destructive">
                  REJECTED{s.rejected_reason ? ` — ${s.rejected_reason}` : ""}
                </span>
              </Row>
            ) : s.unit_price != null && s.gross_amount != null ? (
              <>
                <Row label={t9n("delivery.rate")}>
                  <Money amount={s.unit_price} currency={s.currency ?? ""} />
                </Row>
                <Row label={t9n("field.amount")}>
                  <Money
                    amount={s.gross_amount}
                    currency={s.currency ?? ""}
                    emphasis
                  />
                </Row>
              </>
            ) : (
              <Row label={t9n("delivery.rate")}>
                <span className="text-muted-foreground">
                  {t9n("txDetail.ratePending")}
                </span>
              </Row>
            )}
            <Row label={t9n("txDetail.operator")}>{s.operator_name || "—"}</Row>
          </dl>
        </div>
        <div className="flex flex-wrap justify-center gap-2 print:hidden">
          <Button
            type="button"
            variant="outline"
            onClick={() => window.print()}
          >
            <Printer aria-hidden className="me-1.5 size-4" />
            {t9n("action.print")}
          </Button>
          <Button type="button" variant="outline" onClick={copyText}>
            <Copy aria-hidden className="me-1.5 size-4" />
            {copied ? t9n("txDetail.copied") : t9n("txDetail.copyText")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-end">{children}</dd>
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
  const t9n = useT();
  if (!source) return <span className="text-muted-foreground">—</span>;
  const manual = source === "manual";
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={manual ? "text-muted-foreground" : ""}>
        {source.replace(/_/g, " ")}
      </span>
      {manual ? (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
          {t9n("txDetail.enteredByOperator")}
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
function MoneyTrail({
  tx,
  chain,
}: {
  tx: MilkTransaction;
  chain: Load<CollectionChain>;
}) {
  // DEMO-013: the ORGANIZATION's currency, not a Kenyan default.
  const { currency: orgCurrency, t: t9n } = useLocale();

  if (chain.state === "loading")
    return <LoadingState label={t9n("txDetail.followingMoney")} />;
  if (chain.state === "error")
    return (
      <ErrorState
        message={t9n("txDetail.trailUnavailable", { message: chain.message })}
      />
    );

  const links = chain.data;
  // WO-61: the ROW's own currency first, then the settlement it sits in.
  // The organization is the last resort and reaches only an unpriced
  // collection, which carries no amount for it to mislabel.
  const currency = tx.currency ?? links.settlement?.currency ?? orgCurrency;
  const collected = tx.gross_amount == null ? null : String(tx.gross_amount);
  const contributed = links.settlement
    ? String(links.settlement.line_amount)
    : null;

  // COMPARED, not computed. `sameAmount` normalises two exact-decimal strings
  // and asks whether they denote the same amount — "450.00" and "450.0" do.
  // Subtracting them in JavaScript would be float arithmetic on money, which
  // is the one thing this portal never does.
  const comparable = collected != null && contributed != null;
  const agrees = comparable && sameAmount(collected, contributed);

  const stages: {
    label: string;
    amount: string | null;
    note: string;
    href?: string;
  }[] = [
    {
      label: t9n("txDetail.collection"),
      amount: collected,
      // Deliberately NOT the rate card string: the pricing card above already
      // prints it, and the same identifier twice on one screen reads as two
      // facts.
      note: t9n("txDetail.worthNote"),
    },
    {
      label: t9n("txDetail.settlementContribution"),
      amount: contributed,
      note: links.settlement
        ? `${links.settlement.settlement_number} · ${links.settlement.status}`
        : t9n("txDetail.notSettledShort"),
      href: links.settlement
        ? `/settlements/${links.settlement.id}`
        : undefined,
    },
    {
      label: t9n("txDetail.paymentAllocation"),
      amount: links.payment ? String(links.payment.allocated_amount) : null,
      note: links.payment
        ? `${links.payment.payment_number} · ${links.payment.status}`
        : t9n("txDetail.notPaidShort"),
      href: links.payment ? `/payments/${links.payment.id}` : undefined,
    },
    {
      label: t9n("entity.receipt"),
      amount: links.receipt ? String(links.receipt.net_amount) : null,
      note: links.receipt
        ? `${links.receipt.receipt_number} · ${t9n("txDetail.coversWholePayment")}`
        : t9n("txDetail.noReceiptYet"),
      href: links.payment ? `/payments/${links.payment.id}` : undefined,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <ol className="flex flex-col divide-y">
        {stages.map((stage) => (
          <li
            key={stage.label}
            className="flex items-baseline justify-between gap-4 py-3"
          >
            <div className="flex flex-col">
              {stage.href ? (
                <Link
                  className="text-sm font-medium hover:underline"
                  href={stage.href}
                >
                  {stage.label}
                </Link>
              ) : (
                <span className="text-sm font-medium">{stage.label}</span>
              )}
              <span className="text-xs text-muted-foreground">
                {stage.note}
              </span>
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
            {t9n("txDetail.moneyAgrees", { currency: currency ?? "" })}
          </p>
        ) : (
          <p
            role="alert"
            className="inline-flex items-center gap-2 text-sm font-medium text-destructive"
          >
            <AlertTriangle aria-hidden className="size-4" />
            {t9n("txDetail.moneyMismatch", {
              contributed: contributed ?? "",
              collected: collected ?? "",
              currency: currency ?? "",
            })}
          </p>
        )
      ) : null}
    </div>
  );
}

function PricingBreakdown({ tx }: { tx: MilkTransaction }) {
  const t9n = useT();
  const priced = tx.unit_price != null && tx.gross_amount != null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t9n("report.pricing")}</CardTitle>
        <CardDescription>{t9n("txDetail.pricingHint")}</CardDescription>
      </CardHeader>
      <CardContent>
        {!priced ? (
          <EmptyState
            title={t9n("txDetail.notPriced")}
            description={t9n("txDetail.notPricedHint")}
          />
        ) : (
          <div className="flex flex-col gap-4">
            <dl className="flex flex-col gap-2.5 text-sm">
              <Row label={t9n("txDetail.rateCard")}>
                <span className="text-end text-muted-foreground">
                  {tx.pricing_detail ?? "—"}
                </span>
              </Row>
              <Row label={t9n("field.quantity")}>
                <Quantity value={tx.net_weight} unit={tx.weight_unit ?? "kg"} />
              </Row>
              <Row label={t9n("delivery.rate")}>
                <span className="tabular-nums">
                  {String(tx.unit_price)}
                  <span className="ms-1 text-xs text-muted-foreground">
                    {tx.currency}/{tx.weight_unit ?? "kg"}
                  </span>
                </span>
              </Row>
              {/* BR-0029 / D-3. An override is never silent, so the rate the
                  card resolved sits directly under the rate that was paid —
                  not in a history tab somebody has to think to open. Absent
                  entirely on an ordinary collection. */}
              {tx.base_unit_price != null && (
                <>
                  <Row label={t9n("txDetail.cardRate")}>
                    <span className="tabular-nums text-muted-foreground line-through">
                      {String(tx.base_unit_price)}
                      <span className="ms-1 text-xs">
                        {tx.currency}/{tx.weight_unit ?? "kg"}
                      </span>
                    </span>
                  </Row>
                  <Row label={t9n("txDetail.rateChangedBy")}>
                    <span className="text-end text-muted-foreground">
                      {tx.overridden_by_name ?? tx.overridden_by ?? "—"}
                      {tx.overridden_at ? ` · ${formatStamp(tx.overridden_at)}` : ""}
                    </span>
                  </Row>
                  <Row label={t9n("txDetail.rateChangedWhy")}>
                    <span className="text-end">{tx.override_reason ?? "—"}</span>
                  </Row>
                </>
              )}
            </dl>

            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                {t9n("txDetail.calculation")}
              </p>
              <p className="font-mono text-sm tabular-nums">
                {String(tx.net_weight)} × {String(tx.unit_price)}
              </p>
              <p className="mt-1 font-mono text-sm tabular-nums">
                = {String(tx.gross_amount)} {tx.currency}
              </p>
            </div>

            <div className="flex items-baseline justify-between border-t border-border pt-3">
              <span className="text-sm text-muted-foreground">
                {t9n("txDetail.collectionValue")}
              </span>
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
  linkLabel,
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
  const t9n = useT();
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        {href ? (
          <Link
            className="text-xs underline-offset-4 hover:underline"
            href={href}
          >
            {linkLabel ?? t9n("txDetail.openLink")}
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        {state.state === "loading" ? (
          <LoadingState
            label={t9n("txDetail.loadingThing", {
              what: title.toLowerCase(),
            })}
          />
        ) : state.state === "error" ? (
          <ErrorState
            message={t9n("txDetail.unavailable", { message: state.message })}
          />
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
  const t9n = useT();
  const links = chain.state === "ready" ? chain.data : null;
  const recorded = events.state === "ready" ? (events.data ?? []) : [];

  const later: { label: string; at: string | null; done: boolean }[] = [
    {
      label: links?.settlement
        ? t9n("txDetail.includedInSettlement", {
            number: links.settlement.settlement_number,
          })
        : t9n("txDetail.includedInASettlement"),
      at: null,
      done: Boolean(links?.settlement),
    },
    {
      label: links?.settlement
        ? t9n("txDetail.settlementStatus", {
            status: links.settlement.status,
          })
        : t9n("txDetail.settlementFinalized"),
      at: links?.settlement?.finalized_at ?? null,
      done: links?.settlement?.status === "finalized",
    },
    {
      label: links?.payment
        ? t9n("txDetail.paymentStatus", {
            number: links.payment.payment_number,
            status: links.payment.status,
          })
        : t9n("txDetail.paymentProcessed"),
      at: links?.payment?.paid_at ?? null,
      done: links?.payment?.status === "completed",
    },
    {
      label: links?.receipt
        ? t9n("txDetail.receiptNumber", {
            number: links.receipt.receipt_number,
          })
        : t9n("txDetail.receiptGenerated"),
      at: links?.receipt?.generated_at ?? null,
      done: Boolean(links?.receipt),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t9n("txDetail.lifecycle")}</CardTitle>
        <CardDescription>{t9n("txDetail.lifecycleHint")}</CardDescription>
      </CardHeader>
      <CardContent>
        {events.state === "loading" ? (
          <LoadingState label={t9n("txDetail.loadingTrail")} />
        ) : events.state === "error" ? (
          <ErrorState
            message={t9n("txDetail.trailError", { message: events.message })}
          />
        ) : recorded.length === 0 ? (
          <EmptyState title={t9n("txDetail.noEvents")} />
        ) : (
          <ol className="flex flex-col">
            {recorded.map((event) => (
              <li
                key={`${event.sequence}-${event.event_type}`}
                className="flex gap-3 pb-4 last:pb-0"
              >
                <span className="relative flex flex-col items-center">
                  <span className="mt-1 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15">
                    <Check aria-hidden className="size-3 text-primary" />
                  </span>
                  <span className="mt-1 w-px flex-1 bg-border" />
                </span>
                <span className="flex flex-1 flex-col gap-0.5">
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">
                      {humanise(event.event_type)}
                    </span>
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {stamp(event.created_at)}
                    </span>
                  </span>
                  {/* Who did it, where the platform recorded an actor. An
                      unattributed event says so rather than guessing. */}
                  <span className="text-xs text-muted-foreground">
                    {event.actor_id
                      ? (actorName[event.actor_id] ??
                        t9n("txDetail.operatorId", {
                          id: event.actor_id.slice(0, 8),
                        }))
                      : t9n("txDetail.thePlatform")}
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
                    {stage.done ? (
                      <Check aria-hidden className="size-3 text-primary" />
                    ) : null}
                  </span>
                  <span className="mt-1 w-px flex-1 bg-border" />
                </span>
                <span className="flex flex-1 flex-wrap items-baseline justify-between gap-2">
                  <span
                    className={
                      stage.done
                        ? "text-sm font-medium"
                        : "text-sm text-muted-foreground"
                    }
                  >
                    {stage.label}
                  </span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {stage.done ? stamp(stage.at) : t9n("txDetail.pending")}
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
