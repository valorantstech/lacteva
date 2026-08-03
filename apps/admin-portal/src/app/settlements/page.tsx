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
  Center,
  Settlement,
  SettlementDetail,
  SettlementPageResult,
  Supplier,
  addSettlementCalculation,
  collectSettlementPeriod,
  createSettlement,
  getSettlementDetail,
  listCenters,
  listSettlements,
  listSuppliers,
  removeSettlementLine,
  settlementAction,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = ["", "draft", "calculated", "finalized", "cancelled"] as const;

const statusVariant = (s: Settlement["status"]) =>
  s === "finalized"
    ? "default"
    : s === "cancelled"
      ? "outline"
      : s === "calculated"
        ? "secondary"
        : "secondary";

export default function SettlementsPage() {
  const [page, setPage] = useState<SettlementPageResult | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [centers, setCenters] = useState<Center[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<SettlementDetail | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPage(await listSettlements({ q, status, limit: PAGE_SIZE, offset }));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load settlements");
    }
  }, [q, status, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      listSuppliers({ limit: 100, offset: 0 })
        .then((p) => setSuppliers(p.items))
        .catch(() => setSuppliers([]));
      listCenters({ limit: 100, offset: 0 })
        .then((p) => setCenters(p.items))
        .catch(() => setCenters([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  const supplierName = (id: string) =>
    suppliers.find((s) => s.id === id)?.full_name ?? id.slice(0, 8);

  async function openDetail(id: string) {
    try {
      setDetail(await getSettlementDetail(id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load settlement");
    }
  }

  async function runAction(s: Settlement, action: string) {
    try {
      await settlementAction(s.id, action);
      setError(null);
      await refresh();
      if (detail?.settlement.id === s.id) await openDetail(s.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Action failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  // Dashboard summary from the visible page.
  const counts: Record<string, number> = {};
  for (const s of page?.items ?? []) counts[s.status] = (counts[s.status] ?? 0) + 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settlements</h1>
          <p className="text-sm text-muted-foreground">
            Payable amounts per supplier and period — lifecycle only, no payment yet
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>New settlement</Button>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search settlement number…"
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
        <div className="ml-auto flex gap-2 text-sm">
          {Object.entries(counts).map(([s, n]) => (
            <Badge key={s} variant="outline">
              {s}: {n}
            </Badge>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {showCreate && (
        <SettlementCreateForm
          suppliers={suppliers}
          centers={centers}
          onDone={async () => {
            setShowCreate(false);
            await refresh();
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Number</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Lines</TableHead>
                <TableHead>Net</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-mono">{s.settlement_number}</TableCell>
                  <TableCell>{supplierName(s.supplier_id)}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    {s.period_from} → {s.period_to}
                  </TableCell>
                  <TableCell>{s.line_count}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    {String(s.net_amount)} {s.currency}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(s.status)}>{s.status}</Badge>
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => openDetail(s.id)}>
                      Review
                    </Button>
                    {(s.status === "draft" || s.status === "calculated") && (
                      <Button size="sm" variant="outline" onClick={() => runAction(s, "calculate")}>
                        Calculate
                      </Button>
                    )}
                    {s.status === "calculated" && (
                      <Button size="sm" onClick={() => runAction(s, "finalize")}>
                        Finalize
                      </Button>
                    )}
                    {(s.status === "draft" || s.status === "calculated") && (
                      <Button size="sm" variant="ghost" onClick={() => runAction(s, "cancel")}>
                        Cancel
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No settlements match.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {detail && (
        <SettlementDetailCard
          detail={detail}
          supplierName={supplierName(detail.settlement.supplier_id)}
          onRefresh={async () => {
            await openDetail(detail.settlement.id);
            await refresh();
          }}
          onClose={() => setDetail(null)}
          onError={setError}
        />
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} settlement${page.total === 1 ? "" : "s"}` : "Loading…"}
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

function SettlementDetailCard({
  detail,
  supplierName,
  onRefresh,
  onClose,
  onError,
}: {
  detail: SettlementDetail;
  supplierName: string;
  onRefresh: () => Promise<void>;
  onClose: () => void;
  onError: (e: string) => void;
}) {
  const s = detail.settlement;
  const editable = s.status === "draft" || s.status === "calculated";
  const [calcId, setCalcId] = useState("");

  async function addCalc() {
    try {
      await addSettlementCalculation(s.id, calcId.trim());
      setCalcId("");
      await onRefresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "Add failed");
    }
  }

  async function removeLine(lineId: string) {
    try {
      await removeSettlementLine(s.id, lineId);
      await onRefresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "Remove failed");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          {s.settlement_number}
          <Badge variant={statusVariant(s.status)}>{s.status}</Badge>
          {!detail.totals_match_lines && (
            <Badge variant="destructive">totals out of sync — recalculate</Badge>
          )}
        </CardTitle>
        <CardDescription>
          {supplierName} · {s.period_from} → {s.period_to} · gross {String(s.gross_amount)} ·
          adjustments {String(s.adjustments_amount)} ·{" "}
          <span className="font-medium">
            net {String(s.net_amount)} {s.currency}
          </span>
          {s.finalized_at && ` · finalized ${s.finalized_at.slice(0, 10)}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Quantity</TableHead>
              <TableHead>Unit price</TableHead>
              <TableHead>Gross</TableHead>
              <TableHead>Calculation</TableHead>
              {editable && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {detail.lines.map((line) => (
              <TableRow key={line.id}>
                <TableCell>{line.transaction_date}</TableCell>
                <TableCell>
                  {String(line.quantity)} {line.quantity_unit}
                </TableCell>
                <TableCell>{String(line.unit_price)}</TableCell>
                <TableCell>{String(line.gross_amount)}</TableCell>
                <TableCell className="font-mono text-xs">
                  {line.calculation_id.slice(0, 8)}…
                </TableCell>
                {editable && (
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" onClick={() => removeLine(line.id)}>
                      Remove
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {detail.lines.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No lines yet — add pricing calculations below.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        {editable && (
          <div className="flex items-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                try {
                  const result = await collectSettlementPeriod(s.id);
                  onError(
                    `Collected: ${result.added} added, ${result.skipped} skipped`,
                  );
                  await onRefresh();
                } catch (err) {
                  onError(err instanceof ApiError ? err.detail : "Collect failed");
                }
              }}
            >
              Collect period transactions
            </Button>
            <div className="flex flex-col gap-1">
              <Label htmlFor="s-calc">Pricing calculation ID</Label>
              <Input
                id="s-calc"
                className="h-8 w-96 font-mono"
                placeholder="from the pricing playground or transaction flow"
                value={calcId}
                onChange={(e) => setCalcId(e.target.value)}
              />
            </div>
            <Button size="sm" disabled={!calcId.trim()} onClick={addCalc}>
              Add line
            </Button>
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

function SettlementCreateForm({
  suppliers,
  centers,
  onDone,
  onCancel,
}: {
  suppliers: Supplier[];
  centers: Center[];
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [supplierId, setSupplierId] = useState("");
  const [centerId, setCenterId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [currency, setCurrency] = useState("KES");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createSettlement({
        supplier_id: supplierId,
        center_id: centerId,
        period_from: from,
        period_to: to,
        currency,
      });
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New settlement</CardTitle>
        <CardDescription>
          One settlement per supplier and period — overlapping periods are rejected.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid max-w-2xl grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="st-supplier">Supplier</Label>
            <select
              id="st-supplier"
              required
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
            >
              <option value="">Select…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code} — {s.full_name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="st-center">Collection center</Label>
            <select
              id="st-center"
              required
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              value={centerId}
              onChange={(e) => setCenterId(e.target.value)}
            >
              <option value="">Select…</option>
              {centers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="st-from">Period from</Label>
            <Input
              id="st-from"
              type="date"
              required
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="st-to">Period to</Label>
            <Input
              id="st-to"
              type="date"
              required
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="st-currency">Currency</Label>
            <Input
              id="st-currency"
              required
              minLength={3}
              maxLength={3}
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            />
          </div>
          {error && <p className="col-span-2 text-sm text-destructive">{error}</p>}
          <div className="col-span-2 flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create"}
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
