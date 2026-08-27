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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageContainer } from "@/components/page-container";
import {
  SyncOperation,
  SyncOperationPage,
  SyncStats,
  getSyncStats,
  listSyncOperations,
  retrySyncOperation,
  describeError,
} from "@/lib/api";

const PAGE_SIZE = 15;
const STATUSES = ["", "applied", "duplicate", "conflict", "failed"];

const statusVariant = (s: string) =>
  s === "applied"
    ? "default"
    : s === "failed"
      ? "destructive"
      : s === "conflict"
        ? "secondary"
        : "outline";

/** The operator-facing meaning of each conflict the platform can report. */
const CONFLICT_LABELS: Record<string, string> = {
  already_accepted: "Already recorded on the platform",
  supplier_unavailable: "Supplier is no longer active",
  session_closed: "The collection session was closed",
  rate_card_changed: "Prices changed — collection kept, amount differs",
  unresolved_reference: "Waiting for an earlier step to sync",
  invalid_state: "The platform refused this step",
};

const KIND_LABELS: Record<string, string> = {
  open_session: "Open session",
  close_session: "Close session",
  create_transaction: "Start collection",
  identify_supplier: "Identify supplier",
  receive_milk: "Receive milk",
  capture_weight: "Capture weight",
  capture_quality: "Capture quality",
  accept: "Accept milk",
  reject: "Reject milk",
  complete: "Complete collection",
  cancel: "Cancel collection",
};

const ago = (iso: string | null) => {
  if (!iso) return "never";
  const delta = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
};

export default function SyncMonitorPage() {
  const [page, setPage] = useState<SyncOperationPage | null>(null);
  const [stats, setStats] = useState<SyncStats | null>(null);
  const [status, setStatus] = useState("");
  const [device, setDevice] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<SyncOperation | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [operations, summary] = await Promise.all([
        listSyncOperations({
          status,
          device_id: device,
          limit: PAGE_SIZE,
          offset,
        }),
        getSyncStats(),
      ]);
      setPage(operations);
      setStats(summary);
      setError(null);
    } catch (err) {
      setError(
        describeError(err, "Failed to load sync activity"),
      );
    }
  }, [status, device, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  async function retry(operation: SyncOperation) {
    try {
      const updated = await retrySyncOperation(operation.operation_id);
      setNote(
        `Retried ${KIND_LABELS[operation.kind] ?? operation.kind} — now ${updated.status}.`,
      );
      setError(null);
      await refresh();
    } catch (err) {
      setError(describeError(err, "Retry failed"));
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <PageContainer width="default">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sync monitor</h1>
        <p className="text-sm text-muted-foreground">
          What field devices have replayed after collecting offline. Read-only —
          the record of truth is the collection itself.
        </p>
      </header>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Operations" value={stats.total} />
          <StatCard label="Applied" value={stats.by_status.applied ?? 0} />
          <StatCard
            label="Conflicts"
            value={stats.conflicts}
            tone={stats.conflicts > 0 ? "warn" : undefined}
          />
          <StatCard
            label="Failed"
            value={stats.failed}
            tone={stats.failed > 0 ? "bad" : undefined}
          />
        </div>
      )}

      {stats && stats.devices.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Devices</CardTitle>
            <CardDescription>
              Last sync tells you which centers are collecting into a queue
              rather than the platform.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Device</TableHead>
                  <TableHead>Operations</TableHead>
                  <TableHead>Conflicts</TableHead>
                  <TableHead>Failed</TableHead>
                  <TableHead>Last sync</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.devices.map((d) => (
                  <TableRow key={d.device_id}>
                    <TableCell className="font-mono">{d.device_id}</TableCell>
                    <TableCell>{d.operations}</TableCell>
                    <TableCell
                      className={
                        d.conflicts > 0 ? "font-medium text-orange-600" : ""
                      }
                    >
                      {d.conflicts}
                    </TableCell>
                    <TableCell
                      className={
                        d.failed > 0 ? "font-medium text-destructive" : ""
                      }
                    >
                      {d.failed}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {ago(d.last_sync_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
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
              {s === "" ? "All outcomes" : s}
            </option>
          ))}
        </select>
        <Input
          placeholder="Filter by device id…"
          value={device}
          onChange={(e) => {
            setDevice(e.target.value);
            setOffset(0);
          }}
          className="max-w-xs"
        />
      </div>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Received</TableHead>
                <TableHead>Operation</TableHead>
                <TableHead>Device</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead className="text-end">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((op) => (
                <TableRow key={op.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {op.created_at.slice(0, 16).replace("T", " ")}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {KIND_LABELS[op.kind] ?? op.kind}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {op.device_id || "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(op.status)}>
                      {op.status}
                    </Badge>
                    {op.status === "conflict" && op.applied && (
                      <span className="ms-1 text-xs text-muted-foreground">
                        kept
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-sm truncate text-muted-foreground">
                    {op.conflict_reason
                      ? (CONFLICT_LABELS[op.conflict_reason] ??
                        op.conflict_reason)
                      : (op.error ?? "")}
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSelected(op)}
                    >
                      Inspect
                    </Button>
                    {op.status === "failed" && (
                      <Button size="sm" onClick={() => retry(op)}>
                        Retry
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-center text-muted-foreground"
                  >
                    No device has synchronised yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <OperationDetailCard
          operation={selected}
          onRetry={() => retry(selected)}
          onClose={() => setSelected(null)}
        />
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page
            ? `${page.total} operation${page.total === 1 ? "" : "s"}`
            : "Loading…"}
          {stats?.last_sync_at && ` · last sync ${ago(stats.last_sync_at)}`}
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
    </PageContainer>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "warn" | "bad";
}) {
  return (
    <Card>
      <CardContent className="py-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p
          className={
            tone === "bad"
              ? "text-2xl font-semibold text-destructive"
              : tone === "warn"
                ? "text-2xl font-semibold text-orange-600"
                : "text-2xl font-semibold"
          }
        >
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

function OperationDetailCard({
  operation: op,
  onRetry,
  onClose,
}: {
  operation: SyncOperation;
  onRetry: () => void;
  onClose: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          {KIND_LABELS[op.kind] ?? op.kind}
          <Badge variant={statusVariant(op.status)}>{op.status}</Badge>
          {op.applied && <Badge variant="outline">applied</Badge>}
        </CardTitle>
        <CardDescription>
          device {op.device_id || "—"} · attempt {op.attempts}
          {op.recorded_at &&
            ` · captured ${op.recorded_at.slice(0, 16).replace("T", " ")}`}
          {op.applied_at &&
            ` · applied ${op.applied_at.slice(0, 16).replace("T", " ")}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {op.conflict_reason && (
          <div>
            <p className="font-medium">
              {CONFLICT_LABELS[op.conflict_reason] ?? op.conflict_reason}
            </p>
            <p className="text-muted-foreground">{op.conflict_detail}</p>
          </div>
        )}
        {op.error && (
          <div>
            <p className="font-medium">Error</p>
            <p className="text-destructive">{op.error}</p>
          </div>
        )}
        <div className="font-mono text-xs text-muted-foreground">
          operation {op.operation_id}
          <br />
          local reference {op.client_reference ?? "—"}
          <br />
          target {op.target_ref ?? "—"}
          <br />
          server id {op.server_id ?? "—"}
        </div>
        <div className="flex gap-2">
          {op.status === "failed" && (
            <Button size="sm" onClick={onRetry}>
              Retry
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
