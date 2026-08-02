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
  Supplier,
  SupplierDetail,
  SupplierPage,
  assignSupplierCenter,
  createSupplier,
  getSupplierDetail,
  getSupplierQr,
  listBranches,
  listCenters,
  listSuppliers,
  setSupplierStatus,
  updateSupplier,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = ["", "draft", "active", "suspended", "archived"] as const;

const statusVariant = (s: Supplier["status"]) =>
  s === "active" ? "default" : s === "archived" ? "outline" : "secondary";

type FormState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; supplier: Supplier };

export default function SuppliersPage() {
  const [page, setPage] = useState<SupplierPage | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [centers, setCenters] = useState<Center[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<FormState>({ mode: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<{
    data: SupplierDetail;
    qr: string;
  } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPage(await listSuppliers({ q, status, limit: PAGE_SIZE, offset }));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load suppliers");
    }
  }, [q, status, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      listBranches().then(setBranches).catch(() => setBranches([]));
      listCenters({ limit: 100, offset: 0 })
        .then((p) => setCenters(p.items))
        .catch(() => setCenters([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  async function openDetail(supplier: Supplier) {
    try {
      const [data, qr] = await Promise.all([
        getSupplierDetail(supplier.id),
        getSupplierQr(supplier.id),
      ]);
      setDetail({ data, qr: qr.payload });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load supplier");
    }
  }

  async function changeStatus(supplier: Supplier, next: string) {
    try {
      await setSupplierStatus(supplier.id, next);
      setError(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Status change failed");
    }
  }

  async function assignCenter(supplierId: string, centerId: string) {
    try {
      await assignSupplierCenter(supplierId, centerId);
      const data = await getSupplierDetail(supplierId);
      setDetail((d) => (d ? { ...d, data } : d));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Assignment failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Suppliers</h1>
          <p className="text-sm text-muted-foreground">
            Producers delivering to your collection centers
          </p>
        </div>
        <Button onClick={() => setForm({ mode: "create" })}>New supplier</Button>
      </header>

      <div className="flex gap-3">
        <Input
          placeholder="Search name, code, or phone…"
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
        <SupplierForm
          branches={branches}
          supplier={form.mode === "edit" ? form.supplier : null}
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
                <TableHead>Phone</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-mono">{s.code}</TableCell>
                  <TableCell>{s.full_name}</TableCell>
                  <TableCell>{s.phone}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(s.status)}>{s.status}</Badge>
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => openDetail(s)}>
                      Detail
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setForm({ mode: "edit", supplier: s })}
                    >
                      Edit
                    </Button>
                    {s.status === "draft" && (
                      <Button size="sm" variant="outline" onClick={() => changeStatus(s, "active")}>
                        Activate
                      </Button>
                    )}
                    {s.status === "active" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => changeStatus(s, "suspended")}
                      >
                        Suspend
                      </Button>
                    )}
                    {s.status === "suspended" && (
                      <Button size="sm" variant="outline" onClick={() => changeStatus(s, "active")}>
                        Reinstate
                      </Button>
                    )}
                    {s.status !== "archived" && (
                      <Button size="sm" variant="ghost" onClick={() => changeStatus(s, "archived")}>
                        Archive
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No suppliers match.
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
              {detail.data.supplier.full_name}
              <Badge variant={statusVariant(detail.data.supplier.status)}>
                {detail.data.supplier.status}
              </Badge>
            </CardTitle>
            <CardDescription>
              {detail.data.supplier.code} · {detail.data.profile.village || "no village"} ·{" "}
              {detail.data.bank_accounts.length} bank account(s) ·{" "}
              {detail.data.documents.length} document(s)
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            <div>
              <span className="font-medium">Collection centers:</span>{" "}
              {detail.data.center_ids.length === 0
                ? "none — required before activation"
                : centers
                    .filter((c) => detail.data.center_ids.includes(c.id))
                    .map((c) => c.code)
                    .join(" · ") || `${detail.data.center_ids.length} assigned`}
            </div>
            <div className="flex items-center gap-2">
              <select
                className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                defaultValue=""
                id="assign-center"
              >
                <option value="" disabled>
                  Assign to center…
                </option>
                {centers
                  .filter((c) => !detail.data.center_ids.includes(c.id))
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} — {c.name}
                    </option>
                  ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  const el = document.getElementById("assign-center") as HTMLSelectElement;
                  if (el?.value) void assignCenter(detail.data.supplier.id, el.value);
                }}
              >
                Assign
              </Button>
            </div>
            <div>
              <span className="font-medium">QR payload:</span>{" "}
              <code className="rounded bg-muted px-1 break-all">{detail.qr}</code>
            </div>
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
          {page ? `${page.total} supplier${page.total === 1 ? "" : "s"}` : "Loading…"}
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

function SupplierForm({
  branches,
  supplier,
  onDone,
  onCancel,
}: {
  branches: Branch[];
  supplier: Supplier | null;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [fullName, setFullName] = useState(supplier?.full_name ?? "");
  const [phone, setPhone] = useState(supplier?.phone ?? "");
  const [village, setVillage] = useState("");
  const [branchId, setBranchId] = useState(supplier?.branch_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (supplier) await updateSupplier(supplier.id, { full_name: fullName, phone, village });
      else
        await createSupplier({
          full_name: fullName,
          phone,
          village,
          ...(branchId ? { branch_id: branchId } : {}),
        });
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
        <CardTitle>{supplier ? `Edit ${supplier.code}` : "New supplier"}</CardTitle>
        <CardDescription>
          Suppliers start as drafts; activation requires a collection center assignment.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid max-w-xl grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="s-name">Full name</Label>
            <Input
              id="s-name"
              required
              minLength={2}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="s-phone">Phone</Label>
            <Input id="s-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="s-village">Village</Label>
            <Input id="s-village" value={village} onChange={(e) => setVillage(e.target.value)} />
          </div>
          {!supplier && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="s-branch">Branch (optional)</Label>
              <select
                id="s-branch"
                className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                value={branchId}
                onChange={(e) => setBranchId(e.target.value)}
              >
                <option value="">No branch</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.code} — {b.name}
                  </option>
                ))}
              </select>
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
