"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
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
import { ApiError, type AuditRecord, listAudit } from "@/lib/api";

/**
 * The audit trail (PORTAL-001 / F-10).
 *
 * This is the page an access review reads: SEC-003 made grants AND
 * revocations auditable precisely so that a trail with one and not the other
 * could not misrepresent who still holds what.
 */
export default function AuditPage() {
  const [records, setRecords] = useState<AuditRecord[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRecords(await listAudit(200));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load the audit trail");
    }
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  const shown = (records ?? []).filter((r) =>
    filter ? `${r.action} ${r.resource_type}`.toLowerCase().includes(filter.toLowerCase()) : true,
  );

  return (
    <AdminPage
      title="Audit trail"
      description="What was done, by whom, and when. Newest first. Records are append-only."
      error={error}
    >
      <div className="flex flex-col gap-1.5 sm:max-w-xs">
        <Label htmlFor="filter">Filter by action or resource</Label>
        <Input
          id="filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="authz.role"
        />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>When</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Resource</TableHead>
            <TableHead>Actor</TableHead>
            <TableHead>Detail</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {records === null ? (
            <TableRow>
              <TableCell colSpan={5}>Loading…</TableCell>
            </TableRow>
          ) : shown.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5}>Nothing recorded yet.</TableCell>
            </TableRow>
          ) : (
            shown.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="whitespace-nowrap text-xs">
                  {new Date(r.created_at).toLocaleString()}
                </TableCell>
                <TableCell className="font-mono text-xs">{r.action}</TableCell>
                <TableCell className="text-xs">
                  {r.resource_type}
                  {r.resource_id ? <span className="text-muted-foreground"> · {r.resource_id}</span> : null}
                </TableCell>
                <TableCell className="font-mono text-[11px]">{r.actor_id ?? "system"}</TableCell>
                <TableCell className="max-w-xs truncate text-xs text-muted-foreground">
                  {r.detail ? JSON.stringify(r.detail) : "—"}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </AdminPage>
  );
}
