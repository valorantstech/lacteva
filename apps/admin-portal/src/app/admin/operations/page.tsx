"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, type BackupRun, type BackupStatus, getBackupStatus, listBackupRuns } from "@/lib/api";

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

  const refresh = useCallback(async () => {
    try {
      const [s, history] = await Promise.all([getBackupStatus(), listBackupRuns(20)]);
      setStatus(s);
      setRuns(history);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load backup status");
    }
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  return (
    <AdminPage
      title="Operations"
      description="Is the platform protected? Backup status and recent runs, read-only — restores are an operator procedure, not a button."
      error={error}
    >
      <section className="flex flex-wrap items-center gap-4">
        <Badge variant={status?.healthy ? "default" : "destructive"}>
          {status === null ? "checking…" : status.healthy ? "protected" : "NOT PROTECTED"}
        </Badge>
        <span className="text-sm text-muted-foreground">
          Last backup: {status?.last_backup_at ? new Date(status.last_backup_at).toLocaleString() : "never"}
        </span>
        <span className="text-sm text-muted-foreground">
          Last verified: {status?.last_verified_at ? new Date(status.last_verified_at).toLocaleString() : "never"}
        </span>
      </section>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Started</TableHead>
            <TableHead>Kind</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Finished</TableHead>
            <TableHead>Error</TableHead>
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
                  {new Date(run.started_at).toLocaleString()}
                </TableCell>
                <TableCell>{run.kind}</TableCell>
                <TableCell>
                  <Badge variant={run.status === "succeeded" ? "default" : "destructive"}>
                    {run.status}
                  </Badge>
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}
                </TableCell>
                <TableCell className="max-w-xs truncate text-xs text-destructive">
                  {run.error ?? "—"}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </AdminPage>
  );
}
