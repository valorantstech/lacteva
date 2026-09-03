"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Search, Truck } from "lucide-react";
import {
  ApiError,
  type Center,
  type ReportPage,
  type Supplier,
  type SupplierSummaryRow,
  assignSupplierCenter,
  createSupplier,
  getSupplierReport,
  listCenters,
  listSuppliers,
  setSupplierStatus,
  updateSupplier,
  describeError,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useBusinessToday } from "@/components/date-range";
import { type Column, DataTable } from "@/components/data-table";
import { Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ErrorState } from "@/components/states";
import { PageContainer } from "@/components/page-container";
import { Metric, Surface } from "@/components/surface";

/**
 * Suppliers (DEMO-003).
 *
 * Search, status and centre filters and pagination are all the platform's —
 * `q`, `status`, `center_id`, `limit`, `offset` go to the server. The whole
 * supplier table is never loaded to compute anything, which matters at 24
 * suppliers and matters much more at 24,000.
 *
 * Activity comes from `/v1/reports/collection/by-supplier`, aggregated in SQL.
 */

const PAGE_SIZE = 10;
const STATUSES = ["", "draft", "active", "suspended", "archived"] as const;

type FormState =
  | { mode: "closed" }
  | { mode: "create" }
  | { mode: "edit"; supplier: Supplier };

/**
 * The 30-day activity window, anchored on the DAIRY'S today — not UTC's.
 * `new Date().toISOString()` here was the exact DEMO-019 bug re-introduced:
 * an IST dairy's "last 30 days" was wrong before 05:30 every morning. The
 * date arithmetic runs in UTC ON the business-date string, which is safe
 * because a YYYY-MM-DD has no clock to shift.
 */
function activityWindow(businessToday: string) {
  const to = new Date(`${businessToday}T00:00:00Z`);
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - 29);
  return {
    date_from: from.toISOString().slice(0, 10),
    date_to: businessToday,
  };
}

export default function SuppliersPage() {
  // DERIVED each render (DEMO-019): the timezone arrives after first mount.
  const businessToday = useBusinessToday();
  const [page, setPage] = useState<{ items: Supplier[]; total: number } | null>(
    null,
  );
  const [activity, setActivity] = useState<Record<string, SupplierSummaryRow>>(
    {},
  );
  const [centers, setCenters] = useState<Center[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("");
  const [centerId, setCenterId] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ mode: "closed" });
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listSuppliers({
        q: q || undefined,
        status: status || undefined,
        center_id: centerId || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setPage(result);
      getSupplierReport({ ...activityWindow(businessToday), limit: "100" })
        .then((report: ReportPage<SupplierSummaryRow>) =>
          setActivity(
            Object.fromEntries(
              (report.items ?? []).map((row) => [row.supplier_id, row]),
            ),
          ),
        )
        .catch(() => setActivity({}));
    } catch (err) {
      setError(
        describeError(err, "Could not load suppliers"),
      );
    } finally {
      setLoading(false);
    }
  }, [businessToday, centerId, offset, q, status]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    listCenters({ limit: 100, offset: 0 })
      .then((c) => setCenters(c.items ?? []))
      .catch(() => setCenters([]));
  }, []);

  const activate = async (supplier: Supplier) => {
    setNotice(null);
    try {
      await setSupplierStatus(supplier.id, "active");
      setNotice(`${supplier.full_name} is now active.`);
      void load();
    } catch (err) {
      // BR: a supplier must be assigned to a collection centre before it can
      // be activated. The platform decides; this shows exactly what it said
      // rather than guessing at the reason or hiding the button.
      setNotice(
        err instanceof ApiError
          ? `${supplier.full_name} could not be activated — ${err.detail}`
          : `${supplier.full_name} could not be activated.`,
      );
    }
  };

  const columns: Column<Supplier>[] = [
    {
      key: "name",
      header: "Supplier",
      cell: (s) => (
        <div className="flex flex-col">
          <Link
            className="font-medium hover:underline"
            href={`/suppliers/${s.id}`}
          >
            {s.full_name}
          </Link>
          <span className="text-xs text-muted-foreground">{s.code}</span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (s) => <StatusBadge status={s.status} />,
    },
    {
      key: "phone",
      header: "Phone",
      secondary: true,
      cell: (s) => <span className="text-muted-foreground">{s.phone}</span>,
    },
    {
      key: "collections",
      header: "Collections",
      align: "end",
      cell: (s) => (
        <span className="tabular-nums">
          {activity[s.id]?.deliveries ?? "—"}
        </span>
      ),
    },
    {
      key: "quantity",
      header: "Quantity",
      align: "end",
      cell: (s) =>
        activity[s.id] ? (
          <Quantity value={activity[s.id].total_net_weight_kg} unit={activity[s.id].quantity_unit} />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "value",
      header: "Value",
      align: "end",
      cell: (s) =>
        activity[s.id] ? (
          <Money
            amount={activity[s.id].payable_amount}
            currency={activity[s.id].currency}
          />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "last",
      header: "Last collection",
      secondary: true,
      cell: (s) => {
        const at = activity[s.id]?.last_collection_at;
        return (
          <span className="text-muted-foreground">
            {at ? at.slice(0, 10) : "none"}
          </span>
        );
      },
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (s) => (
        <div className="flex justify-end gap-2">
          {s.status === "draft" || s.status === "suspended" ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => void activate(s)}
            >
              Activate
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setForm({ mode: "edit", supplier: s })}
          >
            Edit
          </Button>
          <Link
            href={`/suppliers/${s.id}`}
            className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
          >
            Open
          </Link>
        </div>
      ),
    },
  ];

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Suppliers"
        description="The producers who deliver milk. Activity figures cover the last 30 days and are computed by the platform."
        actions={
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => (window.location.href = "/suppliers/import")}>
              Import CSV
            </Button>
          <Button type="button" onClick={() => setForm({ mode: "create" })}>
            <Plus aria-hidden className="me-1.5 size-4" />
            New supplier
          </Button>
          </div>
        }
      />

      {/*
        Design System V1: the same three figures, at the size a figure that
        matters deserves. The old `StatTile` rendered them at body scale, which
        is why a page whose whole point is "how many farmers, how many
        delivering" read as a paragraph. That component no longer exists —
        LACTEVA-ADMIN-006 migrated its last user and deleted it.
      */}
      <section aria-label="Supplier summary" className="grid gap-4 sm:grid-cols-3">
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric label="Suppliers" value={String(page?.total ?? 0)} />
          <Truck aria-hidden className="size-4 text-muted-foreground" />
        </Surface>
        <Surface tone="metric">
          <Metric
            label="Active on this page"
            value={String((page?.items ?? []).filter((s) => s.status === "active").length)}
            caption="of the rows shown"
          />
        </Surface>
        <Surface tone="metric">
          <Metric
            label="Delivered recently"
            value={String(Object.keys(activity).length)}
            caption="last 30 days"
          />
        </Surface>
      </section>

      {notice ? (
        <Surface tone="live" role="status" className="px-4 py-3 text-sm">
          {notice}
        </Surface>
      ) : null}

      {form.mode !== "closed" ? (
        <SupplierForm
          state={form}
          centers={centers}
          onClose={() => setForm({ mode: "closed" })}
          onSaved={(message) => {
            setForm({ mode: "closed" });
            setNotice(message);
            void load();
          }}
        />
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Suppliers in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(s) => s.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title:
                q || status || centerId
                  ? "No supplier matches this search"
                  : "No suppliers yet",
              description:
                q || status || centerId
                  ? "Try a different name, code, status or centre."
                  : "Register a supplier, assign them to a centre, then activate them to begin collecting.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="supplier-search">Search</Label>
                  <div className="relative">
                    <Search
                      aria-hidden
                      className="pointer-events-none absolute left-2 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    />
                    <Input
                      id="supplier-search"
                      className="w-64 ps-8"
                      placeholder="Name, code or phone"
                      value={q}
                      onChange={(e) => {
                        setQ(e.target.value);
                        setOffset(0);
                      }}
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="supplier-status">Status</Label>
                  <Select
                    id="supplier-status"
                    value={status}
                    onChange={(e) => {
                      setStatus(e.target.value as (typeof STATUSES)[number]);
                      setOffset(0);
                    }}
                  >
                    {STATUSES.map((s) => (
                      <option key={s || "all"} value={s}>
                        {s || "All statuses"}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="supplier-center">Centre</Label>
                  <Select
                    id="supplier-center"
                    value={centerId}
                    onChange={(e) => {
                      setCenterId(e.target.value);
                      setOffset(0);
                    }}
                  >
                    <option value="">All centres</option>
                    {centers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </Select>
                </div>
              </>
            }
            page={{
              offset,
              limit: PAGE_SIZE,
              total: page?.total ?? 0,
              onChange: setOffset,
              busy: loading,
            }}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function SupplierForm({
  state,
  centers,
  onClose,
  onSaved,
}: {
  state: Exclude<FormState, { mode: "closed" }>;
  centers: Center[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const editing = state.mode === "edit";
  const [fullName, setFullName] = useState(
    editing ? state.supplier.full_name : "",
  );
  const [phone, setPhone] = useState(editing ? state.supplier.phone : "");
  const [centerId, setCenterId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const errors: Record<string, string> = {};
    if (fullName.trim().length < 2)
      errors.fullName = "Enter the supplier's full name.";
    if (!/^\+?\d{7,15}$/.test(phone.trim()))
      errors.phone =
        "Enter a phone number, digits only, optionally starting with +.";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setBusy(true);
    setError(null);
    try {
      if (editing) {
        await updateSupplier(state.supplier.id, {
          full_name: fullName.trim(),
          phone: phone.trim(),
        });
        onSaved(`${fullName.trim()} updated.`);
      } else {
        const created = await createSupplier({
          full_name: fullName.trim(),
          phone: phone.trim(),
        });
        if (centerId) await assignSupplierCenter(created.id, centerId);
        onSaved(
          centerId
            ? `${created.full_name} created and assigned to a centre. Activate them when ready.`
            : `${created.full_name} created as a draft. Assign a centre before activating.`,
        );
      }
    } catch (err) {
      setError(
        describeError(err, "The supplier could not be saved"),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
          <h2 className="text-base font-semibold">
            {editing ? `Edit ${state.supplier.full_name}` : "New supplier"}
          </h2>
          {error ? <ErrorState message={error} /> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="supplier-name">
                Full name
                <span aria-hidden className="ms-0.5 text-destructive">
                  *
                </span>
                <span className="sr-only"> (required)</span>
              </Label>
              <Input
                id="supplier-name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                aria-invalid={Boolean(fieldErrors.fullName)}
                placeholder="Amina Njoroge"
              />
              {fieldErrors.fullName ? (
                <p role="alert" className="text-xs text-destructive">
                  {fieldErrors.fullName}
                </p>
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="supplier-phone">
                Phone
                <span aria-hidden className="ms-0.5 text-destructive">
                  *
                </span>
                <span className="sr-only"> (required)</span>
              </Label>
              <Input
                id="supplier-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                aria-invalid={Boolean(fieldErrors.phone)}
                placeholder="+254700000001"
              />
              {fieldErrors.phone ? (
                <p role="alert" className="text-xs text-destructive">
                  {fieldErrors.phone}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Used to notify them about payments.
                </p>
              )}
            </div>

            {!editing ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="supplier-form-center">Collection centre</Label>
                <Select
                  id="supplier-form-center"
                  width="full"
                  value={centerId}
                  onChange={(e) => setCenterId(e.target.value)}
                >
                  <option value="">Assign later</option>
                  {centers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground">
                  A supplier must be assigned to a centre before they can be
                  activated.
                </p>
              </div>
            ) : null}
          </div>

          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : editing ? "Save changes" : "Create supplier"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
