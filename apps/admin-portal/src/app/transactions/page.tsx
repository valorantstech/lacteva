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
  MilkTransaction,
  MilkTransactionPage,
  TransactionEvent,
  getMilkTransactionEvents,
  listCenters,
  listMilkTransactions,
} from "@/lib/api";

const PAGE_SIZE = 15;
const STATES = [
  "",
  "NEW",
  "SUPPLIER_IDENTIFIED",
  "MILK_RECEIVED",
  "QUALITY_PENDING",
  "PRICED",
  "ACCEPTED",
  "REJECTED",
  "COMPLETED",
  "CANCELLED",
] as const;

const stateVariant = (s: string) =>
  s === "COMPLETED"
    ? "default"
    : s === "CANCELLED" || s === "REJECTED"
      ? "destructive"
      : "secondary";

export default function TransactionsPage() {
  const [page, setPage] = useState<MilkTransactionPage | null>(null);
  const [centers, setCenters] = useState<Center[]>([]);
  const [state, setState] = useState("");
  const [centerId, setCenterId] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<{
    tx: MilkTransaction;
    events: TransactionEvent[];
  } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPage(
        await listMilkTransactions({
          state: state || undefined,
          center_id: centerId || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load transactions");
    }
  }, [state, centerId, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 100);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      listCenters({ limit: 100, offset: 0 })
        .then((p) => setCenters(p.items))
        .catch(() => setCenters([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  async function openDetail(tx: MilkTransaction) {
    try {
      const events = await getMilkTransactionEvents(tx.id);
      setDetail({ tx, events });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load timeline");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Milk Collection Transactions
        </h1>
        <p className="text-sm text-muted-foreground">
          Immutable collection records — corrections become adjustment transactions
        </p>
      </header>

      <div className="flex gap-3">
        <select
          className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setOffset(0);
          }}
        >
          {STATES.map((s) => (
            <option key={s} value={s}>
              {s === "" ? "All states" : s}
            </option>
          ))}
        </select>
        <select
          className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
          value={centerId}
          onChange={(e) => {
            setCenterId(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All centers</option>
          {centers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Milk</TableHead>
                <TableHead className="text-right">Net kg</TableHead>
                <TableHead className="text-right">FAT</TableHead>
                <TableHead className="text-right">SNF</TableHead>
                <TableHead className="text-right">Timeline</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Badge variant={stateVariant(t.state)}>{t.state}</Badge>
                  </TableCell>
                  <TableCell>{t.milk_type ?? "—"}</TableCell>
                  <TableCell className="text-right">{t.net_weight ?? "—"}</TableCell>
                  <TableCell className="text-right">{t.fat ?? "—"}</TableCell>
                  <TableCell className="text-right">{t.snf ?? "—"}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" onClick={() => openDetail(t)}>
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No transactions match.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {detail && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              Transaction timeline
              <Badge variant={stateVariant(detail.tx.state)}>{detail.tx.state}</Badge>
            </CardTitle>
            <CardDescription>
              {detail.tx.id} · net {detail.tx.net_weight ?? "—"} kg ·{" "}
              {detail.tx.pricing_status ?? "no pricing"}
              {detail.tx.rejected_reason
                ? ` · rejected: ${detail.tx.rejected_reason}`
                : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <ol className="relative ml-3 flex flex-col gap-3 border-l border-border pl-5">
              {detail.events.map((e) => (
                <li key={e.sequence} className="text-sm">
                  <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
                  <span className="font-medium">{e.event_type}</span>{" "}
                  <span className="text-muted-foreground">
                    · {new Date(e.created_at).toLocaleTimeString()} ·{" "}
                    {String(e.data.state ?? "")}
                  </span>
                </li>
              ))}
            </ol>
            <div>
              <Button size="sm" variant="ghost" onClick={() => setDetail(null)}>
                Close
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} transaction${page.total === 1 ? "" : "s"}` : "Loading…"}
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
