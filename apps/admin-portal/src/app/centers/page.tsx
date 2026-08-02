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
  Branch,
  Center,
  CenterPage,
  Device,
  ReadinessResult,
  createCenter,
  getReadiness,
  listBranches,
  listCenterDevices,
  listCenters,
  setCenterStatus,
  updateCenter,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = ["", "active", "inactive", "maintenance", "archived"] as const;

const statusVariant = (s: Center["status"]) =>
  s === "active" ? "default" : s === "archived" ? "outline" : "secondary";

type FormState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; center: Center };

export default function CentersPage() {
  const [page, setPage] = useState<CenterPage | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<FormState>({ mode: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<{
    center: Center;
    result: ReadinessResult;
    devices: Device[];
  } | null>(null);

  async function showReadiness(center: Center) {
    try {
      const [result, devices] = await Promise.all([
        getReadiness(center.id),
        listCenterDevices(center.id),
      ]);
      setReadiness({ center, result, devices: devices.items });
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Readiness evaluation failed");
    }
  }

  const refresh = useCallback(async () => {
    try {
      setPage(await listCenters({ q, status, limit: PAGE_SIZE, offset }));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load centers");
    }
  }, [q, status, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150); // debounce search typing
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      listBranches()
        .then(setBranches)
        .catch(() => setBranches([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  async function changeStatus(center: Center, next: string) {
    try {
      await setCenterStatus(center.id, next);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Status change failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Collection Centers</h1>
          <p className="text-sm text-muted-foreground">
            Facility management — status, hours, and calendars live per center
          </p>
        </div>
        <Button onClick={() => setForm({ mode: "create" })}>New center</Button>
      </header>

      <div className="flex gap-3">
        <Input
          placeholder="Search by name or code…"
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
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {form.mode !== "closed" && (
        <CenterForm
          branches={branches}
          center={form.mode === "edit" ? form.center : null}
          onDone={async () => {
            setForm({ mode: "closed" });
            await refresh();
          }}
          onCancel={() => setForm({ mode: "closed" })}
        />
      )}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Timezone</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono">{c.code}</TableCell>
                  <TableCell>{c.name}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(c.status)}>{c.status}</Badge>
                  </TableCell>
                  <TableCell>{c.timezone}</TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => showReadiness(c)}>
                      Readiness
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setForm({ mode: "edit", center: c })}
                    >
                      Edit
                    </Button>
                    {c.status !== "archived" && (
                      <>
                        {c.status !== "active" && (
                          <Button size="sm" variant="outline" onClick={() => changeStatus(c, "active")}>
                            Activate
                          </Button>
                        )}
                        {c.status === "active" && (
                          <Button size="sm" variant="outline" onClick={() => changeStatus(c, "inactive")}>
                            Deactivate
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => changeStatus(c, "archived")}>
                          Archive
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No centers match.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {readiness && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              Readiness — {readiness.center.code}
              <Badge
                variant={
                  readiness.result.status === "READY"
                    ? "default"
                    : readiness.result.status === "WARNING"
                      ? "secondary"
                      : "destructive"
                }
              >
                {readiness.result.status}
              </Badge>
            </CardTitle>
            <CardDescription>
              Evaluated {new Date(readiness.result.evaluated_at).toLocaleTimeString()} ·{" "}
              {readiness.devices.length} device(s) at this center
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <ul className="flex flex-col gap-2">
              {readiness.result.checks.map((check) => (
                <li key={check.rule} className="flex items-center justify-between text-sm">
                  <span>
                    <span className={check.passed ? "text-green-600" : "text-destructive"}>
                      {check.passed ? "✓" : "✗"}
                    </span>{" "}
                    <span className="font-mono">{check.rule}</span>{" "}
                    <span className="text-muted-foreground">— {check.detail}</span>
                  </span>
                  <Badge variant={check.severity === "blocking" ? "outline" : "secondary"}>
                    {check.severity}
                  </Badge>
                </li>
              ))}
            </ul>
            {readiness.devices.length > 0 && (
              <div className="text-sm text-muted-foreground">
                Devices:{" "}
                {readiness.devices
                  .map((d) => `${d.category} ${d.serial_number} (${d.status})`)
                  .join(" · ")}
              </div>
            )}
            <div>
              <Button size="sm" variant="ghost" onClick={() => setReadiness(null)}>
                Close
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} center${page.total === 1 ? "" : "s"}` : "Loading…"}
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
            {currentPage} / {totalPages}
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

function CenterForm({
  branches,
  center,
  onDone,
  onCancel,
}: {
  branches: Branch[];
  center: Center | null;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(center?.name ?? "");
  const [code, setCode] = useState(center?.code ?? "");
  const [timezone, setTimezone] = useState(center?.timezone ?? "UTC");
  const [branchId, setBranchId] = useState(center?.branch_id ?? branches[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (center) await updateCenter(center.id, { name, timezone });
      else await createCenter({ branch_id: branchId, name, code });
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{center ? `Edit ${center.code}` : "New collection center"}</CardTitle>
        <CardDescription>
          {center
            ? "Name and timezone are editable; code and branch are fixed at creation."
            : "A center belongs to exactly one branch for its whole life."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid max-w-xl grid-cols-2 gap-4">
          {!center && (
            <div className="col-span-2 flex flex-col gap-1.5">
              <Label htmlFor="branch">Branch</Label>
              <select
                id="branch"
                required
                className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                value={branchId}
                onChange={(e) => setBranchId(e.target.value)}
              >
                <option value="" disabled>
                  Select a branch…
                </option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.code} — {b.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {!center ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="code">Code</Label>
              <Input id="code" required value={code} onChange={(e) => setCode(e.target.value)} />
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tz">Timezone</Label>
              <Input id="tz" required value={timezone} onChange={(e) => setTimezone(e.target.value)} />
            </div>
          )}
          {error && <p className="col-span-2 text-sm text-destructive">{error}</p>}
          <div className="col-span-2 flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save"}
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
