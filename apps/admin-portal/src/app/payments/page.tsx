"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  BalancePageResult,
  PAYMENT_METHODS,
  Payment,
  PaymentDetail,
  PaymentPageResult,
  SettlementBalance,
  Supplier,
  createPayment,
  getPaymentDetail,
  listOutstandingBalances,
  listPayments,
  listSuppliers,
  paymentAction,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = ["", "draft", "pending", "processing", "completed", "failed", "cancelled"];

const statusVariant = (s: string) =>
  s === "completed"
    ? "default"
    : s === "failed"
      ? "destructive"
      : s === "cancelled"
        ? "outline"
        : "secondary";

const money = (v: string | number, currency: string) => `${String(v)} ${currency}`;

export default function PaymentsPage() {
  const [page, setPage] = useState<PaymentPageResult | null>(null);
  const [balances, setBalances] = useState<BalancePageResult | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<PaymentDetail | null>(null);
  const [payFor, setPayFor] = useState<SettlementBalance | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [payments, owed] = await Promise.all([
        listPayments({ q, status, method, limit: PAGE_SIZE, offset }),
        listOutstandingBalances({ limit: 50, offset: 0 }),
      ]);
      setPage(payments);
      setBalances(owed);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load payments");
    }
  }, [q, status, method, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    listSuppliers({ limit: 100, offset: 0 })
      .then((p) => setSuppliers(p.items))
      .catch(() => setSuppliers([]));
  }, []);

  const supplierName = (id: string) =>
    suppliers.find((s) => s.id === id)?.full_name ?? id.slice(0, 8);

  async function openDetail(id: string) {
    try {
      setDetail(await getPaymentDetail(id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load payment");
    }
  }

  async function act(
    payment: Payment,
    action: "submit" | "execute" | "retry" | "complete" | "fail" | "cancel",
    body: Record<string, string> = {},
  ) {
    try {
      const updated = await paymentAction(payment.id, action, body);
      setNote(`${payment.payment_number} is now ${updated.status}.`);
      setError(null);
      await refresh();
      if (detail?.payment.id === payment.id) await openDetail(payment.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Action failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const owedTotal = (balances?.items ?? []).reduce(
    (sum, b) => sum + Number(b.outstanding),
    0,
  );

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Payments</h1>
        <p className="text-sm text-muted-foreground">
          Money moved against finalized settlements — settlements are never modified
        </p>
      </header>

      <OutstandingPanel
        balances={balances}
        supplierName={supplierName}
        owedTotal={owedTotal}
        onPay={setPayFor}
      />

      {payFor && (
        <NewPaymentForm
          balance={payFor}
          supplierName={supplierName(payFor.supplier_id)}
          onDone={async () => {
            setPayFor(null);
            await refresh();
          }}
          onCancel={() => setPayFor(null)}
        />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search payment number or reference…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          className="max-w-xs"
        />
        <select
          className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s === "" ? "All statuses" : s}
            </option>
          ))}
        </select>
        <select
          className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          value={method}
          onChange={(e) => {
            setMethod(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All methods</option>
          {PAYMENT_METHODS.map((m) => (
            <option key={m} value={m}>
              {m.replace("_", " ").toLowerCase()}
            </option>
          ))}
        </select>
      </div>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Payment history</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Number</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Method</TableHead>
                <TableHead>Settlements</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono">{p.payment_number}</TableCell>
                  <TableCell>{supplierName(p.supplier_id)}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    {money(p.amount, p.currency)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {p.method.replace("_", " ").toLowerCase()}
                  </TableCell>
                  <TableCell>{p.line_count}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(p.status)}>{p.status}</Badge>
                    {p.attempt_count > 1 && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        ×{p.attempt_count}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => openDetail(p.id)}>
                      Inspect
                    </Button>
                    <PaymentActions payment={p} onAct={act} />
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No payments match.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {detail && (
        <PaymentDetailCard
          detail={detail}
          supplierName={supplierName(detail.payment.supplier_id)}
          onAct={act}
          onClose={() => setDetail(null)}
        />
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} payment${page.total === 1 ? "" : "s"}` : "Loading…"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <span>
            {Math.floor(offset / PAGE_SIZE) + 1} / {totalPages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={!page || offset + PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </footer>
    </main>
  );
}

/** The settlement selector: what is still owed, and the button that pays it. */
function OutstandingPanel({
  balances,
  supplierName,
  owedTotal,
  onPay,
}: {
  balances: BalancePageResult | null;
  supplierName: (id: string) => string;
  owedTotal: number;
  onPay: (b: SettlementBalance) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3 text-base">
          Outstanding balances
          {balances && balances.total > 0 && (
            <Badge variant="secondary">
              {balances.total} settlement{balances.total === 1 ? "" : "s"} · {owedTotal.toFixed(2)}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Finalized settlements with money still owed. A draft payment already reserves its
          allocation, so nothing here can be paid twice.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Settlement</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Payable</TableHead>
              <TableHead>Allocated</TableHead>
              <TableHead>Paid</TableHead>
              <TableHead>Outstanding</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {balances?.items.map((b) => (
              <TableRow key={b.settlement_id}>
                <TableCell className="font-mono">{b.settlement_number}</TableCell>
                <TableCell>{supplierName(b.supplier_id)}</TableCell>
                <TableCell>{money(b.payable, b.currency)}</TableCell>
                <TableCell className="text-muted-foreground">{String(b.allocated)}</TableCell>
                <TableCell className="text-muted-foreground">{String(b.paid)}</TableCell>
                <TableCell className="font-medium">{money(b.outstanding, b.currency)}</TableCell>
                <TableCell className="text-right">
                  <Button size="sm" onClick={() => onPay(b)}>
                    Pay
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {balances && balances.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  Nothing outstanding — every finalized settlement is paid or allocated.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function PaymentActions({
  payment,
  onAct,
}: {
  payment: Payment;
  onAct: (
    p: Payment,
    a: "submit" | "execute" | "retry" | "complete" | "fail" | "cancel",
    body?: Record<string, string>,
  ) => Promise<void>;
}) {
  const s = payment.status;
  return (
    <>
      {s === "draft" && (
        <Button size="sm" variant="outline" onClick={() => onAct(payment, "submit")}>
          Submit
        </Button>
      )}
      {s === "pending" && (
        <Button size="sm" variant="outline" onClick={() => onAct(payment, "execute")}>
          Execute
        </Button>
      )}
      {s === "processing" && (
        <>
          <Button size="sm" onClick={() => onAct(payment, "complete")}>
            Complete
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              onAct(payment, "fail", { reason: "reported failed by the operator" })
            }
          >
            Mark failed
          </Button>
        </>
      )}
      {s === "failed" && (
        <Button size="sm" onClick={() => onAct(payment, "retry")}>
          Retry
        </Button>
      )}
      {(s === "draft" || s === "pending" || s === "failed") && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onAct(payment, "cancel", { reason: "cancelled from the portal" })}
        >
          Cancel
        </Button>
      )}
    </>
  );
}

function PaymentDetailCard({
  detail,
  supplierName,
  onAct,
  onClose,
}: {
  detail: PaymentDetail;
  supplierName: string;
  onAct: (
    p: Payment,
    a: "submit" | "execute" | "retry" | "complete" | "fail" | "cancel",
    body?: Record<string, string>,
  ) => Promise<void>;
  onClose: () => void;
}) {
  const p = detail.payment;
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          {p.payment_number}
          <Badge variant={statusVariant(p.status)}>{p.status}</Badge>
          <Badge variant="outline">{p.method.replace("_", " ").toLowerCase()}</Badge>
          {!detail.totals_match_lines && (
            <Badge variant="destructive">amount does not match its allocations</Badge>
          )}
        </CardTitle>
        <CardDescription>
          {supplierName} · <span className="font-medium">{money(p.amount, p.currency)}</span>
          {p.reference && ` · ref ${p.reference}`}
          {p.completed_at && ` · completed ${p.completed_at.slice(0, 10)}`}
          {p.failure_reason && ` · last failure: ${p.failure_reason}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        <div>
          <p className="mb-1 font-medium">Allocations</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Settlement</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.lines.map((line) => (
                <TableRow key={line.id}>
                  <TableCell className="font-mono">{line.settlement_number}</TableCell>
                  <TableCell className="text-right">
                    {money(line.amount, p.currency)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div>
          <p className="mb-1 font-medium">Attempts</p>
          {detail.attempts.length === 0 ? (
            <p className="text-muted-foreground">Not executed yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>Reference</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Failure</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.attempts.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>{a.attempt_number}</TableCell>
                    <TableCell>{a.provider}</TableCell>
                    <TableCell className="font-mono text-xs">{a.reference ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(a.status)}>{a.status}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {a.started_at.slice(0, 16).replace("T", " ")}
                    </TableCell>
                    <TableCell className="text-destructive">{a.failure_reason ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {p.status !== "completed" && p.status !== "cancelled" && (
          <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
            <div className="flex flex-col gap-1">
              <Label htmlFor="p-ref">Reference</Label>
              <Input
                id="p-ref"
                className="h-8 w-56"
                placeholder="bank / cheque / M-Pesa code"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="p-reason">Failure or cancel reason</Label>
              <Input
                id="p-reason"
                className="h-8 w-64"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            {p.status === "processing" && (
              <>
                <Button
                  size="sm"
                  onClick={() =>
                    onAct(p, "complete", reference ? { reference } : {})
                  }
                >
                  Complete
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!reason.trim()}
                  onClick={() => onAct(p, "fail", { reason: reason.trim() })}
                >
                  Mark failed
                </Button>
              </>
            )}
            {p.status === "failed" && (
              <Button
                size="sm"
                onClick={() => onAct(p, "retry", reference ? { reference } : {})}
              >
                Retry
              </Button>
            )}
            {(p.status === "draft" || p.status === "pending" || p.status === "failed") && (
              <Button
                size="sm"
                variant="ghost"
                disabled={!reason.trim()}
                onClick={() => onAct(p, "cancel", { reason: reason.trim() })}
              >
                Cancel payment
              </Button>
            )}
          </div>
        )}

        <div>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function NewPaymentForm({
  balance,
  supplierName,
  onDone,
  onCancel,
}: {
  balance: SettlementBalance;
  supplierName: string;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [method, setMethod] = useState<string>("BANK_TRANSFER");
  const [amount, setAmount] = useState(String(balance.outstanding));
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const partial = Number(amount) < Number(balance.outstanding);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createPayment({
        supplier_id: balance.supplier_id,
        currency: balance.currency,
        method,
        allocations: [{ settlement_id: balance.settlement_id, amount }],
        reference: reference || undefined,
        note: note || undefined,
      });
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not create the payment");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pay {balance.settlement_number}</CardTitle>
        <CardDescription>
          {supplierName} · outstanding {money(balance.outstanding, balance.currency)}. Pay less
          than the outstanding amount to make a partial payment — the remainder stays payable.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid max-w-2xl grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-method">Method</Label>
            <select
              id="np-method"
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              {PAYMENT_METHODS.map((m) => (
                <option key={m} value={m}>
                  {m.replace("_", " ").toLowerCase()}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-amount">Amount ({balance.currency})</Label>
            <Input
              id="np-amount"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            {partial && (
              <span className="text-xs text-muted-foreground">
                Partial — {(Number(balance.outstanding) - Number(amount)).toFixed(2)} stays
                outstanding
              </span>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-ref">Reference</Label>
            <Input
              id="np-ref"
              placeholder="bank / cheque / M-Pesa code"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-note">Note</Label>
            <Input id="np-note" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="col-span-2 text-sm text-destructive">{error}</p>}
          <div className="col-span-2 flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create payment"}
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
