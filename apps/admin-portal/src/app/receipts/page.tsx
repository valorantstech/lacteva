"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { formatAmount } from "@/components/money";
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
  Receipt,
  ReceiptDetail,
  ReceiptPageResult,
  RenderedReceipt,
  getReceiptDetail,
  listReceipts,
  receiptAction,
  renderReceipt,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = ["", "generated", "delivered", "archived"];
const FORMATS = ["json", "html", "pdf"] as const;

const statusVariant = (s: string) =>
  s === "delivered" ? "default" : s === "archived" ? "outline" : "secondary";

// DEMO-010: through the shared formatter, so a receipt reads `1,176.00 KES`
// like every other amount on the platform. It used to print the raw string.
const money = (v: string | number, currency: string) => `${formatAmount(v)} ${currency}`;

export default function ReceiptsPage() {
  const [page, setPage] = useState<ReceiptPageResult | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPage(await listReceipts({ q, status, limit: PAGE_SIZE, offset }));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load receipts");
    }
  }, [q, status, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  async function openDetail(id: string) {
    try {
      setDetail(await getReceiptDetail(id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load receipt");
    }
  }

  async function act(receipt: Receipt, action: "deliver" | "archive") {
    try {
      const updated = await receiptAction(receipt.id, action);
      setNote(`${receipt.receipt_number} is now ${updated.status}.`);
      setError(null);
      await refresh();
      if (detail?.receipt.id === receipt.id) await openDetail(receipt.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Action failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Receipts</h1>
        <p className="text-sm text-muted-foreground">
          Immutable proof of payment, generated automatically when a payment completes.
          Nothing here can be edited or deleted.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search receipt, payment, supplier or reference…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          className="max-w-sm"
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
      </div>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Receipt</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Paid</TableHead>
                <TableHead>Payment</TableHead>
                <TableHead>Settlements</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono">{r.receipt_number}</TableCell>
                  <TableCell>
                    {r.supplier_name || r.supplier_id.slice(0, 8)}
                    {r.supplier_code && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        {r.supplier_code}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap font-medium">
                    {money(r.net_amount, r.currency)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap font-mono text-xs">
                    {/* DEMO-006: no dead ends — the receipt reaches its payment. */}
                    <Link className="hover:underline" href={`/payments/${r.payment_id}`}>
                      {r.payment_number}
                    </Link>
                  </TableCell>
                  <TableCell>{r.line_count}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => openDetail(r.id)}>
                      View
                    </Button>
                    {r.status === "generated" && (
                      <Button size="sm" variant="outline" onClick={() => act(r, "deliver")}>
                        Mark delivered
                      </Button>
                    )}
                    {r.status !== "archived" && (
                      <Button size="sm" variant="ghost" onClick={() => act(r, "archive")}>
                        Archive
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No receipts yet — they appear when a payment completes.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {detail && <ReceiptDetailCard detail={detail} onClose={() => setDetail(null)} />}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} receipt${page.total === 1 ? "" : "s"}` : "Loading…"}
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

function ReceiptDetailCard({
  detail,
  onClose,
}: {
  detail: ReceiptDetail;
  onClose: () => void;
}) {
  const r = detail.receipt;
  const [format, setFormat] = useState<string>("html");
  const [preview, setPreview] = useState<RenderedReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function render(next: string) {
    setFormat(next);
    setBusy(true);
    setError(null);
    try {
      setPreview(await renderReceipt(r.id, next));
    } catch (err) {
      setPreview(null);
      setError(err instanceof ApiError ? err.detail : "Could not render this format");
    } finally {
      setBusy(false);
    }
  }

  /** The API needs the bearer token, so fetch through the client and save the
   *  rendered body locally rather than linking straight at the endpoint. */
  async function download() {
    setBusy(true);
    setError(null);
    try {
      const rendered = await renderReceipt(r.id, format);
      const blob = new Blob([rendered.body], { type: rendered.content_type });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = rendered.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Download failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          {r.receipt_number}
          <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
          <Badge variant="outline">v{r.version}</Badge>
        </CardTitle>
        <CardDescription>
          {r.supplier_name} ({r.supplier_code}) ·{" "}
          <span className="font-medium">{money(r.net_amount, r.currency)} paid</span> · payment{" "}
          <Link className="underline underline-offset-4" href={`/payments/${r.payment_id}`}>
            {r.payment_number}
          </Link>{" "}
          ({r.payment_method.replace("_", " ").toLowerCase()})
          {r.payment_reference && ` · ref ${r.payment_reference}`}
          {r.delivered_at && ` · delivered ${r.delivered_at.slice(0, 10)}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        <div>
          <p className="mb-1 font-medium">Settlements covered</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Settlement</TableHead>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Gross</TableHead>
                <TableHead className="text-right">Adjustments</TableHead>
                <TableHead className="text-right">Paid</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.lines.map((line) => (
                <TableRow key={line.id}>
                  <TableCell className="font-mono">
                    <Link className="hover:underline" href={`/settlements/${line.settlement_id}`}>
                      {line.settlement_number}
                    </Link>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {line.period_from} → {line.period_to}
                  </TableCell>
                  <TableCell className="text-right">{String(line.gross_amount)}</TableCell>
                  <TableCell className="text-right">
                    {String(line.adjustments_amount)}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {String(line.amount_paid)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">Preview</span>
          {FORMATS.map((f) => (
            <Button
              key={f}
              size="sm"
              variant={format === f ? "default" : "outline"}
              disabled={busy}
              onClick={() => render(f)}
            >
              {f.toUpperCase()}
            </Button>
          ))}
          <Button size="sm" variant="outline" disabled={busy} onClick={download}>
            Download
          </Button>
          {preview?.placeholder && (
            <Badge variant="secondary">placeholder — no PDF engine is integrated</Badge>
          )}
        </div>

        {error && <p className="text-destructive">{error}</p>}

        {preview && (
          <div>
            {preview.format === "html" ? (
              <iframe
                title={`Receipt ${r.receipt_number}`}
                srcDoc={preview.body}
                sandbox=""
                className="h-96 w-full rounded-lg border border-border bg-white"
              />
            ) : (
              <pre className="max-h-96 overflow-auto rounded-lg bg-muted p-3 text-xs">
                {preview.body}
              </pre>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              {preview.filename} · {preview.content_type}
            </p>
          </div>
        )}

        <div>
          <p className="mb-1 font-medium">Trace</p>
          <p className="font-mono text-xs text-muted-foreground">
            payment {detail.reference.payment_id}
            <br />
            settlements {detail.reference.settlement_numbers.join(", ")}
            <br />
            source event {detail.reference.source_event_id ?? "—"}
            <br />
            formats available: {detail.metadata.available_formats.join(", ")}
          </p>
        </div>

        <div>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
