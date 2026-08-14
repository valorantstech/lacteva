"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Receipt as ReceiptIcon,
  RotateCcw,
  User,
  XCircle,
} from "lucide-react";
import {
  ApiError,
  type Payment,
  type PaymentDetail,
  type Receipt,
  getPaymentDetail,
  listReceipts,
  paymentAction,
  receiptDownloadUrl,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/**
 * One payment, end to end (DEMO-006).
 *
 * A payment on this platform RECORDS money movement; it does not perform it.
 * That distinction is the whole design of this screen. "Execute" opens an
 * attempt against a provider; a human or an integration then reports back
 * whether it succeeded, and `complete` or `fail` records that answer. Nothing
 * here simulates a bank.
 *
 * Which is why the failure path is real. `fail` is the platform's own
 * transition — processing → failed, with a mandatory reason, closing the
 * attempt and releasing the allocation so the settlement is payable again. The
 * portal does not fake a failure, does not hide one, and does not invent a
 * reason: the operator types why, and the platform stores it on the payment and
 * on the attempt that failed.
 *
 * Attempts are never reused (BR-0019). A retry opens attempt N+1, and the
 * history below shows every one — including the ones that failed. That list is
 * the audit trail, not a summary of it.
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

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 19).replace("T", " ") : "—";

/**
 * Exactly the payment service's transitions — no button the backend rejects.
 * Note `cancel`: deliberately impossible while processing, because money may
 * already be in flight and the truthful sequence is fail-then-cancel.
 */
function allowed(p: Payment) {
  return {
    submit: p.status === "draft",
    execute: p.status === "pending",
    retry: p.status === "failed",
    complete: p.status === "processing",
    fail: p.status === "processing",
    cancel: p.status === "draft" || p.status === "pending" || p.status === "failed",
  };
}

export default function PaymentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<Load<PaymentDetail>>(LOADING);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  // Free text the operator supplies to the platform, never invented here.
  const [form, setForm] = useState<"execute" | "complete" | "fail" | "cancel" | "retry" | null>(
    null,
  );
  const [provider, setProvider] = useState("");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await getPaymentDetail(id);
      setDetail({ state: "ready", data: d });
      // A receipt only exists once the payment completed; the absence of one is
      // information, not an error.
      listReceipts({ payment_id: id, limit: 10, offset: 0 })
        .then((r) => setReceipts(r.items ?? []))
        .catch(() => setReceipts([]));
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

  /** Act, then re-read — including after a refusal. See the settlement page. */
  async function run(label: string, action: () => Promise<unknown>, success: string) {
    setBusy(label);
    setFailure(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      setForm(null);
      setProvider("");
      setReference("");
      setReason("");
    } catch (err) {
      setFailure(describe(err));
    } finally {
      setBusy(null);
      await load();
    }
  }

  if (detail.state === "loading") return <LoadingState label="Loading payment…" />;
  if (detail.state === "error")
    return (
      <div className="mx-auto w-full max-w-6xl p-4 sm:p-6 lg:p-8">
        <ErrorState
          message={`This payment could not be loaded — ${detail.message}.`}
          action={
            <Link className="text-sm underline underline-offset-4" href="/payments">
              Back to payments
            </Link>
          }
        />
      </div>
    );

  const { payment: p, lines, attempts, totals_match_lines } = detail.data;
  const can = allowed(p);
  const terminal = p.status === "completed" || p.status === "cancelled";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title={p.payment_number}
        description={`${p.method}${p.reference ? ` · ${p.reference}` : ""} · created ${stamp(p.created_at)}`}
        actions={<StatusBadge status={p.status} />}
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

      {/* The failure the platform itself recorded — shown where it happened. */}
      {p.status === "failed" && p.failure_reason ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3"
        >
          <XCircle aria-hidden className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div>
            <p className="text-sm font-medium text-destructive">
              This payment failed on {stamp(p.failed_at)}
            </p>
            <p className="text-sm text-muted-foreground">{p.failure_reason}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              The allocation has been released — the settlement is payable again, either by retrying
              this payment or by raising a new one.
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Amount</CardTitle>
            <CardDescription>
              The stored amount and its allocations, exactly as the platform holds them.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-3xl font-semibold">
              <Money amount={p.amount} currency={p.currency} />
            </p>
            {totals_match_lines ? (
              <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                <CheckCircle2 aria-hidden className="size-4" />
                Still equals its {p.line_count} {p.line_count === 1 ? "allocation" : "allocations"} —
                verified by the platform.
              </p>
            ) : (
              <p
                role="alert"
                className="inline-flex items-center gap-2 text-sm font-medium text-destructive"
              >
                <AlertTriangle aria-hidden className="size-4" />
                The stored amount no longer equals its allocations.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Payment</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <User aria-hidden className="size-3.5" /> Supplier
                </dt>
                <dd>
                  <Link className="hover:underline" href={`/suppliers/${p.supplier_id}`}>
                    View supplier
                  </Link>
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-muted-foreground">Method</dt>
                <dd>{p.method}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-muted-foreground">Reference</dt>
                <dd className="font-mono text-xs">{p.reference || "—"}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-muted-foreground">Attempts</dt>
                <dd className="tabular-nums">{p.attempt_count}</dd>
              </div>
              {p.completed_at ? (
                <div className="flex items-start justify-between gap-4">
                  <dt className="text-muted-foreground">Completed</dt>
                  <dd className="tabular-nums">{stamp(p.completed_at)}</dd>
                </div>
              ) : null}
              {p.cancelled_at ? (
                <div className="flex items-start justify-between gap-4">
                  <dt className="text-muted-foreground">Cancelled</dt>
                  <dd className="tabular-nums">{stamp(p.cancelled_at)}</dd>
                </div>
              ) : null}
              {p.note ? (
                <div className="flex flex-col gap-1">
                  <dt className="text-muted-foreground">Note</dt>
                  <dd>{p.note}</dd>
                </div>
              ) : null}
            </dl>
          </CardContent>
        </Card>
      </div>

      {/* --- Lifecycle ---------------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Operations</CardTitle>
          <CardDescription>
            {terminal
              ? p.status === "completed"
                ? "This payment is completed. It is terminal and immutable — a correction is a new payment or an adjustment."
                : "This payment is cancelled. No further operation is possible."
              : "This platform records money movement; it does not perform it. Executing opens an attempt against a provider — then record what actually happened."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {terminal ? null : (
            <div className="flex flex-wrap gap-2">
              {can.submit ? (
                <Button
                  type="button"
                  disabled={busy !== null}
                  onClick={() =>
                    void run(
                      "submit",
                      () => paymentAction(p.id, "submit"),
                      "Payment approved for execution.",
                    )
                  }
                >
                  {busy === "submit" ? "Submitting…" : "Approve for execution"}
                </Button>
              ) : null}
              {can.execute ? (
                <Button type="button" disabled={busy !== null} onClick={() => setForm("execute")}>
                  Execute
                </Button>
              ) : null}
              {can.retry ? (
                <Button type="button" disabled={busy !== null} onClick={() => setForm("retry")}>
                  <RotateCcw aria-hidden className="me-1.5 size-4" />
                  Retry
                </Button>
              ) : null}
              {can.complete ? (
                <Button type="button" disabled={busy !== null} onClick={() => setForm("complete")}>
                  Record success
                </Button>
              ) : null}
              {can.fail ? (
                <Button
                  type="button"
                  variant="destructive"
                  disabled={busy !== null}
                  onClick={() => setForm("fail")}
                >
                  Record failure
                </Button>
              ) : null}
              {can.cancel ? (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => setForm("cancel")}
                >
                  Cancel payment
                </Button>
              ) : null}
            </div>
          )}

          {p.status === "processing" ? (
            <p className="text-xs text-muted-foreground">
              A processing payment cannot be cancelled — money may already be in flight. Record the
              failure first, then cancel.
            </p>
          ) : null}

          {form === "execute" || form === "retry" ? (
            <form
              className="flex flex-wrap items-end gap-2 rounded-md border p-4"
              onSubmit={(e) => {
                e.preventDefault();
                const action = form;
                void run(
                  action,
                  () =>
                    paymentAction(p.id, action, {
                      ...(provider ? { provider } : {}),
                      ...(reference ? { reference } : {}),
                    }),
                  action === "retry"
                    ? "New attempt opened. The previous attempt is kept."
                    : "Execution started — the payment is now processing.",
                );
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay-provider">Provider</Label>
                <Input
                  id="pay-provider"
                  className="w-56"
                  placeholder="e.g. mpesa-b2c"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay-reference">Reference</Label>
                <Input
                  id="pay-reference"
                  className="w-56"
                  placeholder="provider transaction id"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={busy !== null}>
                {busy ? "Working…" : form === "retry" ? "Open new attempt" : "Start execution"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setForm(null)}>
                Cancel
              </Button>
            </form>
          ) : null}

          {form === "complete" ? (
            <form
              className="flex flex-col gap-3 rounded-md border p-4"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  "complete",
                  () => paymentAction(p.id, "complete", reference ? { reference } : {}),
                  "Payment completed. A receipt is generated from the platform's own event.",
                );
              }}
            >
              <p className="inline-flex items-start gap-2 text-sm">
                <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-600" />
                <span>
                  Recording success for <Money amount={p.amount} currency={p.currency} /> is
                  permanent. A completed payment cannot be edited or reversed — a correction has to
                  be a new payment or an adjustment.
                </span>
              </p>
              <div className="flex flex-wrap items-end gap-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pay-done-ref">Provider reference</Label>
                  <Input
                    id="pay-done-ref"
                    className="w-64"
                    placeholder="optional"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                  />
                </div>
                <Button type="submit" disabled={busy !== null}>
                  {busy === "complete" ? "Recording…" : "Yes, record as completed"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setForm(null)}>
                  Not yet
                </Button>
              </div>
            </form>
          ) : null}

          {form === "fail" || form === "cancel" ? (
            <form
              className="flex flex-wrap items-end gap-2 rounded-md border border-destructive/40 p-4"
              onSubmit={(e) => {
                e.preventDefault();
                const action = form;
                void run(
                  action,
                  () => paymentAction(p.id, action, { reason }),
                  action === "fail"
                    ? "Failure recorded. The allocation is released and the payment can be retried."
                    : "Payment cancelled. The allocation is released.",
                );
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay-reason">
                  {form === "fail" ? "What went wrong?" : "Why is this payment cancelled?"}
                </Label>
                <Input
                  id="pay-reason"
                  required
                  className="w-96"
                  placeholder={
                    form === "fail" ? "e.g. provider rejected: invalid account" : "reason"
                  }
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Stored on the payment and on the attempt. The platform requires a reason.
                </p>
              </div>
              <Button type="submit" variant="destructive" disabled={busy !== null || !reason}>
                {form === "fail" ? "Confirm failure" : "Confirm cancellation"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setForm(null)}>
                Back
              </Button>
            </form>
          ) : null}
        </CardContent>
      </Card>

      {/* --- What this payment settles ------------------------------------ */}
      <Card>
        <CardHeader>
          <CardTitle>Settlements paid</CardTitle>
          <CardDescription>
            Each allocation names the settlement it discharges, and links to it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No allocations on this payment.</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {lines.map((line) => (
                <li key={line.id} className="flex items-center justify-between gap-4 py-3">
                  <Link
                    className="font-medium hover:underline"
                    href={`/settlements/${line.settlement_id}`}
                  >
                    {line.settlement_number}
                  </Link>
                  <Money amount={line.amount} currency={p.currency} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* --- Every attempt, including the failures ------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Attempt history</CardTitle>
          <CardDescription>
            Attempts are never reused (BR-0019) — a retry opens a new one, and every previous
            attempt stays exactly as it ended.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {attempts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No attempt yet — this payment has not been executed.
            </p>
          ) : (
            <ol className="flex flex-col divide-y">
              {attempts.map((a) => (
                <li key={a.id} className="flex flex-col gap-1 py-3">
                  <div className="flex items-center justify-between gap-4">
                    <span className="font-medium">
                      Attempt {a.attempt_number} · {a.provider}
                    </span>
                    <StatusBadge status={a.status} />
                  </div>
                  <span className="text-xs text-muted-foreground">
                    started {stamp(a.started_at)}
                    {a.completed_at ? ` · ended ${stamp(a.completed_at)}` : ""}
                    {a.reference ? ` · ${a.reference}` : ""}
                  </span>
                  {a.failure_reason ? (
                    <span className="text-sm text-destructive">{a.failure_reason}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      {/* --- The receipt -------------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle>Receipt</CardTitle>
          <CardDescription>
            A receipt is generated from the platform&apos;s own `payment.completed` event, not by
            this page.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {receipts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {p.status === "completed"
                ? "No receipt has been generated for this payment yet."
                : "A receipt appears once this payment completes."}
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {receipts.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex flex-col">
                    <span className="inline-flex items-center gap-1.5 font-medium">
                      <ReceiptIcon aria-hidden className="size-3.5" />
                      {r.receipt_number}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      v{r.version} · {r.status} · issued {stamp(r.generated_at)}
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
          )}
        </CardContent>
      </Card>
    </div>
  );
}
