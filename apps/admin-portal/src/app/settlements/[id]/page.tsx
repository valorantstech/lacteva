"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Download,
  Lock,
  Receipt as ReceiptIcon,
  User,
} from "lucide-react";
import {
  ApiError,
  type Payment,
  type Receipt,
  type Settlement,
  type SettlementBalance,
  type SettlementDetail,
  type SettlementLine,
  collectSettlementPeriod,
  getSettlementBalance,
  getSettlementDetail,
  listPayments,
  listReceipts,
  receiptDownloadUrl,
  settlementAction,
} from "@/lib/api";
import { formatStamp } from "@/components/datetime";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * One settlement, end to end (DEMO-006).
 *
 * Three rules keep this screen honest, and each one exists because the
 * dishonest version is easier to write:
 *
 * 1. NO ARITHMETIC. Gross, adjustments and net are three strings the platform
 *    stored. The portal prints them; it never adds a column of lines to check,
 *    because a browser that agreed with itself would hide a platform that
 *    disagreed. `totals_match_lines` is the platform's OWN answer to that
 *    question, and when it is false this page says so in red.
 *
 * 2. NO BUTTON THE BACKEND WILL REJECT. The settlement service permits
 *    collect/calculate/cancel only while open (draft or calculated), and
 *    finalize only from `calculated` with at least one line. `allowed()` below
 *    mirrors exactly those guards — so a finalized settlement shows no
 *    lifecycle buttons at all, which is what BR-0010 means in a user interface.
 *
 * 3. FINALIZING ASKS FIRST. It is the one irreversible action here: a finalized
 *    settlement cannot be edited, recalculated, or even cancelled. The
 *    confirmation states that plainly and requires a second click.
 */

type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

const LOADING = { state: "loading" } as const;

/** The business reason when the platform gave one, the HTTP detail otherwise. */
const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Request failed";
};

/** One definition, shared with every other screen. */
const stamp = formatStamp;

/** Exactly the settlement service's own guards — nothing more permissive. */
function allowed(s: Settlement) {
  const open = s.status === "draft" || s.status === "calculated";
  return {
    collect: open,
    calculate: open,
    finalize: s.status === "calculated" && s.line_count > 0,
    cancel: open,
  };
}

export default function SettlementDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<Load<SettlementDetail>>(LOADING);
  const [balance, setBalance] = useState<SettlementBalance | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await getSettlementDetail(id);
      setDetail({ state: "ready", data: d });

      // Downstream money. A finalized settlement has a balance; any settlement
      // may already have payments allocated against it. Neither is required
      // for the page to be useful, so neither may break it.
      if (d.settlement.status === "finalized") {
        getSettlementBalance(id)
          .then(setBalance)
          .catch(() => setBalance(null));
      } else {
        setBalance(null);
      }
      // Payments allocated to THIS settlement — the platform filters, not the
      // portal. Receipts hang off a payment, not a settlement, so they are
      // fetched per payment: a bounded handful, and the only way to reach them
      // without inventing a link the domain does not have.
      listPayments({ settlement_id: id, limit: 50, offset: 0 })
        .then(async (p) => {
          const items = p.items ?? [];
          setPayments(items);
          const found = await Promise.all(
            items.map((pay) =>
              listReceipts({ payment_id: pay.id, limit: 10, offset: 0 })
                .then((r) => r.items ?? [])
                .catch(() => []),
            ),
          );
          setReceipts(found.flat());
        })
        .catch(() => {
          setPayments([]);
          setReceipts([]);
        });
    } catch (err) {
      setDetail({ state: "error", message: describe(err) });
    }
  }, [id]);

  useEffect(() => {
    // Deferred by a tick: a synchronous setState inside an effect body cascades
    // renders, and the lint rule that says so is right.
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  /**
   * Every lifecycle action goes through here, and every one of them re-reads
   * the settlement afterwards — including after a refusal. The platform is the
   * authority on what state this settlement is in; a portal that kept its own
   * copy after being told "no" would show buttons for a world that no longer
   * exists.
   */
  async function run(label: string, action: () => Promise<unknown>, success: string) {
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

  if (detail.state === "loading") return <LoadingState label="Loading settlement…" />;
  if (detail.state === "error")
    return (
      <div className="mx-auto w-full max-w-6xl p-4 sm:p-6 lg:p-8">
        <ErrorState
          message={`This settlement could not be loaded — ${detail.message}.`}
          action={
            <Link className="text-sm underline underline-offset-4" href="/settlements">
              Back to settlements
            </Link>
          }
        />
      </div>
    );

  const { settlement: s, lines, totals_match_lines } = detail.data;
  const can = allowed(s);
  const anyAction = can.collect || can.calculate || can.finalize || can.cancel;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title={s.settlement_number}
        description={`Settlement period ${s.period_from} → ${s.period_to}`}
        actions={
          <span className="inline-flex items-center gap-2">
            <StatusBadge status={s.status} />
            {s.status === "finalized" ? (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Lock aria-hidden className="size-3" /> immutable
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
        <p role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          The platform refused: {failure}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Financial summary</CardTitle>
            <CardDescription>
              Every figure below was computed and stored by the platform. This page performs no
              arithmetic.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <dl className="grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-sm text-muted-foreground">Gross</dt>
                <dd className="text-lg font-semibold">
                  <Money amount={s.gross_amount} currency={s.currency} />
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Adjustments</dt>
                <dd className="text-lg font-semibold">
                  <Money amount={s.adjustments_amount} currency={s.currency} />
                </dd>
                <p className="text-xs text-muted-foreground">fixed at zero by BR-0011</p>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Net payable</dt>
                <dd className="text-lg font-semibold">
                  <Money amount={s.net_amount} currency={s.currency} />
                </dd>
              </div>
            </dl>

            {totals_match_lines ? (
              <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                <CheckCircle2 aria-hidden className="size-4" />
                Stored totals still match the {s.line_count}{" "}
                {s.line_count === 1 ? "line" : "lines"} — verified by the platform.
              </p>
            ) : (
              <p
                role="alert"
                className="inline-flex items-center gap-2 text-sm font-medium text-destructive"
              >
                <AlertTriangle aria-hidden className="size-4" />
                Stored totals no longer match the lines. Recalculate before finalizing.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Settlement</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <User aria-hidden className="size-3.5" /> Supplier
                </dt>
                <dd>
                  <Link className="hover:underline" href={`/suppliers/${s.supplier_id}`}>
                    View supplier
                  </Link>
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <Building2 aria-hidden className="size-3.5" /> Centre
                </dt>
                <dd>
                  <Link className="hover:underline" href={`/centers/${s.center_id}`}>
                    View centre
                  </Link>
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-muted-foreground">Period</dt>
                <dd className="tabular-nums">
                  {s.period_from} → {s.period_to}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-muted-foreground">Currency</dt>
                <dd>{s.currency}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-muted-foreground">Created</dt>
                <dd className="tabular-nums">{stamp(s.created_at)}</dd>
              </div>
              {s.finalized_at ? (
                <div className="flex items-start justify-between gap-4">
                  <dt className="text-muted-foreground">Finalized</dt>
                  <dd className="tabular-nums">{stamp(s.finalized_at)}</dd>
                </div>
              ) : null}
              {s.cancelled_at ? (
                <div className="flex items-start justify-between gap-4">
                  <dt className="text-muted-foreground">Cancelled</dt>
                  <dd className="tabular-nums">{stamp(s.cancelled_at)}</dd>
                </div>
              ) : null}
            </dl>
          </CardContent>
        </Card>
      </div>

      {/* --- Lifecycle ---------------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Lifecycle</CardTitle>
          <CardDescription>
            {anyAction
              ? "Collect the period's completed collections, total them, then finalize."
              : s.status === "finalized"
                ? "This settlement is finalized. BR-0010 makes it immutable — it cannot be edited, recalculated, or cancelled."
                : "This settlement is cancelled. No further operation is possible."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {anyAction ? (
            <div className="flex flex-wrap gap-2">
              {can.collect ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() =>
                    void run(
                      "collect",
                      async () => {
                        const r = await collectSettlementPeriod(s.id);
                        setNotice(
                          `Collected ${r.added} ${r.added === 1 ? "collection" : "collections"}; ${r.skipped} already settled or ineligible.`,
                        );
                      },
                      "Collection sweep complete.",
                    )
                  }
                >
                  {busy === "collect" ? "Collecting…" : "Collect period"}
                </Button>
              ) : null}
              {can.calculate ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() =>
                    void run(
                      "calculate",
                      () => settlementAction(s.id, "calculate"),
                      "Totals recalculated from the lines.",
                    )
                  }
                >
                  {busy === "calculate" ? "Calculating…" : "Calculate totals"}
                </Button>
              ) : null}
              {can.finalize ? (
                <Button type="button" disabled={busy !== null} onClick={() => setConfirming(true)}>
                  Finalize
                </Button>
              ) : null}
              {can.cancel ? (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => setCancelling((v) => !v)}
                >
                  Cancel settlement
                </Button>
              ) : null}
            </div>
          ) : null}

          {/* Finalizing is the one irreversible step. It asks. */}
          {confirming ? (
            <div className="flex flex-col gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-4">
              <p className="inline-flex items-start gap-2 text-sm font-medium">
                <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
                <span>
                  Finalizing {s.settlement_number} is permanent. Once finalized this settlement
                  cannot be edited, recalculated, or cancelled — a correction has to be a new
                  settlement or an adjustment. Its net payable of{" "}
                  <Money amount={s.net_amount} currency={s.currency} /> becomes what the supplier is
                  owed.
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
                      "finalize",
                      () => settlementAction(s.id, "finalize"),
                      "Settlement finalized. It is now immutable and payable.",
                    );
                  }}
                >
                  {busy === "finalize" ? "Finalizing…" : "Yes, finalize permanently"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                  Keep it open
                </Button>
              </div>
            </div>
          ) : null}

          {cancelling ? (
            <form
              className="flex flex-wrap items-end gap-2 rounded-md border p-4"
              onSubmit={(e) => {
                e.preventDefault();
                setCancelling(false);
                void run(
                  "cancel",
                  () => settlementAction(s.id, "cancel", { reason: cancelReason }),
                  "Settlement cancelled.",
                );
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cancel-reason">Reason</Label>
                <Input
                  id="cancel-reason"
                  className="w-80"
                  maxLength={300}
                  placeholder="Why is this settlement being abandoned?"
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                />
              </div>
              <Button type="submit" variant="destructive" disabled={busy !== null}>
                Confirm cancellation
              </Button>
              <Button type="button" variant="ghost" onClick={() => setCancelling(false)}>
                Keep it
              </Button>
            </form>
          ) : null}
        </CardContent>
      </Card>

      {/* --- Money owed and paid ------------------------------------------ */}
      {balance ? (
        <Card>
          <CardHeader>
            <CardTitle>Payment position</CardTitle>
            <CardDescription>
              Allocated counts every live payment, including drafts — an intent reserves the money,
              so a second payment can never be built on it.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-4">
              <div>
                <dt className="text-sm text-muted-foreground">Payable</dt>
                <dd className="font-semibold">
                  <Money amount={balance.payable} currency={balance.currency} />
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Allocated</dt>
                <dd className="font-semibold">
                  <Money amount={balance.allocated} currency={balance.currency} />
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Paid</dt>
                <dd className="font-semibold">
                  <Money amount={balance.paid} currency={balance.currency} />
                </dd>
              </div>
              <div>
                <dt className="text-sm text-muted-foreground">Outstanding</dt>
                <dd className="font-semibold">
                  <Money amount={balance.outstanding} currency={balance.currency} />
                </dd>
                {balance.fully_paid ? (
                  <p className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <CheckCircle2 aria-hidden className="size-3" /> fully paid
                  </p>
                ) : null}
              </div>
            </dl>
          </CardContent>
        </Card>
      ) : null}

      {payments.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Payments against this settlement</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y">
              {payments.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex flex-col">
                    <Link className="font-medium hover:underline" href={`/payments/${p.id}`}>
                      {p.payment_number}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {p.method}
                      {p.reference ? ` · ${p.reference}` : ""} · {stamp(p.created_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Money amount={p.amount} currency={p.currency} />
                    <StatusBadge status={p.status} />
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {receipts.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Receipts</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y">
              {receipts.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex flex-col">
                    <Link className="font-medium hover:underline" href={`/payments/${r.payment_id}`}>
                      <ReceiptIcon aria-hidden className="me-1.5 inline size-3.5" />
                      {r.receipt_number}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {r.payment_number} · issued {stamp(r.generated_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Money amount={r.net_amount} currency={r.currency} />
                    <a
                      className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
                      href={receiptDownloadUrl(r.id, r.render_format)}
                    >
                      <Download aria-hidden className="me-1.5 size-3.5" />
                      Download
                    </a>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {/* --- The collections this settlement is made of --------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Collections included</CardTitle>
          <CardDescription>
            {s.line_count === 0
              ? "No collections yet. Collect the period to sweep in every completed, priced, unsettled collection."
              : `${s.line_count} ${s.line_count === 1 ? "collection" : "collections"} — each one links back to the delivery it came from.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing settled here yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Collections settled by {s.settlement_number}</caption>
                <thead>
                  <tr className="border-b text-start text-muted-foreground">
                    <th className="py-2 pe-4 font-medium">Date</th>
                    <th className="py-2 pe-4 font-medium">Collection</th>
                    <th className="py-2 pe-4 text-end font-medium">Quantity</th>
                    <th className="py-2 pe-4 text-end font-medium">Rate</th>
                    <th className="py-2 pe-4 text-end font-medium">Gross</th>
                    <th className="py-2 font-medium">Trace</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line: SettlementLine) => (
                    <tr key={line.id} className="border-b last:border-0">
                      <td className="py-2 pe-4 tabular-nums">{String(line.transaction_date).slice(0, 10)}</td>
                      <td className="py-2 pe-4">
                        {line.transaction_id ? (
                          <Link
                            className="hover:underline"
                            href={`/transactions/${line.transaction_id}`}
                          >
                            {line.transaction_id.slice(0, 8)}…
                          </Link>
                        ) : (
                          <span className="text-muted-foreground">calculation only</span>
                        )}
                      </td>
                      <td className="py-2 pe-4 text-end">
                        <Quantity value={line.quantity} unit={line.quantity_unit} />
                      </td>
                      <td className="py-2 pe-4 text-end tabular-nums">{String(line.unit_price)}</td>
                      <td className="py-2 pe-4 text-end">
                        <Money amount={line.gross_amount} currency={s.currency} />
                      </td>
                      <td className="py-2 font-mono text-xs text-muted-foreground">
                        {line.trace_reference}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
