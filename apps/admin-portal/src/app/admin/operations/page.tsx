"use client";

import { useCallback, useEffect, useState } from "react";
import { formatStamp } from "@/components/datetime";
import { AdminPage } from "@/components/admin-page";
import { Badge } from "@/components/ui/badge";
import { TableSkeleton } from "@/components/states";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type BackupRun,
  type BackupStatus,
  getBackupStatus,
  listBackupRuns,
  describeError,
} from "@/lib/api";

/**
 * Backup visibility (PORTAL-001 / F-10).
 *
 * Read-only, deliberately. The platform can take a backup and restore one,
 * but a restore is not a button: DEPLOYMENT.md walks an operator through it
 * with the database quiesced. Showing whether the platform is protected is
 * useful; offering a one-click restore from a browser is not.
 */
export default function OperationsPage() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [runs, setRuns] = useState<BackupRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  // LACTEVA-ADMIN-001: until the first fetch settles this page does not know
  // whether there are no runs or simply no answer yet, and it was saying the
  // former. `runs` starts `[]`, so emptiness alone cannot tell them apart.
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [s, history] = await Promise.all([
        getBackupStatus(),
        listBackupRuns(20),
      ]);
      setStatus(s);
      setRuns(history);
      setError(null);
    } catch (err) {
      setError(
        describeError(err, "Failed to load backup status"),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  // Design System V1 (batch F): the quiet-label treatment `DataTable` gives
  // its column headers, applied here because this page uses the raw `Table`
  // primitive. Kept page-local for the same reason as the /admin/users pilot —
  // `DataTable` already styles its own heads, so pushing this into `TableHead`
  // would double the treatment everywhere else.
  return (
    <AdminPage
      title="Operations"
      description="Is the platform protected? Backup status and recent runs, read-only — restores are an operator procedure, not a button."
      error={error}
    >
      <section className="flex flex-wrap items-center gap-4">
        <Badge variant={status?.healthy ? "default" : "destructive"}>
          {status === null
            ? "checking…"
            : status.healthy
              ? "protected"
              : "NOT PROTECTED"}
        </Badge>
        <span className="text-sm text-muted-foreground">
          Last backup:{" "}
          {status?.last_backup_at
            ? formatStamp(status.last_backup_at)
            : "never"}
        </span>
        <span className="text-sm text-muted-foreground">
          Last verified:{" "}
          {status?.last_verified_at
            ? formatStamp(status.last_verified_at)
            : "never"}
        </span>
      </section>

      {loading && runs.length === 0 ? (
        <TableSkeleton columns={5} rows={5} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Started
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Kind
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Status
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Finished
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Error
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5}>No backup runs recorded.</TableCell>
              </TableRow>
            ) : (
              runs.map((run) => (
                <TableRow key={run.id}>
                  <TableCell className="whitespace-nowrap text-xs">
                    {formatStamp(run.started_at)}
                  </TableCell>
                  <TableCell>{run.kind}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        run.status === "succeeded" ? "default" : "destructive"
                      }
                    >
                      {run.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs">
                    {formatStamp(run.finished_at)}
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-xs text-destructive">
                    {run.error ?? "—"}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </AdminPage>
  );
}
