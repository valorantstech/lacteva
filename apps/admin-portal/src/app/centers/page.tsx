"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Building2, Plus, Search } from "lucide-react";
import {
  ApiError,
  type Branch,
  type Center,
  type CenterSummaryRow,
  type ReportPage,
  createCenter,
  getCenterReport,
  listBranches,
  listCenters,
  setCenterStatus,
  updateCenter,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import { Money, Quantity } from "@/components/money";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ErrorState } from "@/components/states";

/**
 * Collection centres (DEMO-003).
 *
 * The list is the platform's own paginated, searchable, status-filtered centre
 * endpoint — `q`, `status`, `limit` and `offset` all go to the server, so the
 * browser never holds the table in order to narrow it.
 *
 * The ACTIVITY columns come from a second source: `/v1/reports/collection/by-center`,
 * which aggregates quantity, value and last activity in SQL. Joining them here
 * is presentation, not calculation — nothing on this page adds up a number the
 * platform has not already added up.
 */

const PAGE_SIZE = 10;
const STATUSES = ["", "active", "inactive", "maintenance", "archived"] as const;
const TIMEZONE = /^[A-Za-z]+\/[A-Za-z_+-]+$/;

type FormState =
  { mode: "closed" } | { mode: "create" } | { mode: "edit"; center: Center };

/** The window the activity figures cover. Long enough that a demo looks alive. */
function activityWindow() {
  const to = new Date();
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - 29);
  return {
    date_from: from.toISOString().slice(0, 10),
    date_to: to.toISOString().slice(0, 10),
  };
}

export default function CentersPage() {
  const [page, setPage] = useState<{ items: Center[]; total: number } | null>(
    null,
  );
  const [activity, setActivity] = useState<Record<string, CenterSummaryRow>>(
    {},
  );
  const [branches, setBranches] = useState<Branch[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ mode: "closed" });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listCenters({
        q: q || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setPage(result);
      // Activity is a separate concern and a separate failure: a reporting
      // hiccup must not stop the centre list itself from rendering.
      getCenterReport({ ...activityWindow(), limit: "100" })
        .then((report: ReportPage<CenterSummaryRow>) =>
          setActivity(
            Object.fromEntries(
              (report.items ?? []).map((row) => [row.center_id, row]),
            ),
          ),
        )
        .catch(() => setActivity({}));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Could not load collection centres",
      );
    } finally {
      setLoading(false);
    }
  }, [offset, q, status]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    listBranches()
      .then((b) => setBranches(b ?? []))
      .catch(() => setBranches([]));
  }, []);

  const totals = useMemo(() => {
    const rows = Object.values(activity);
    return {
      centers: page?.total ?? 0,
      active: (page?.items ?? []).filter((c) => c.status === "active").length,
      reporting: rows.length,
    };
  }, [activity, page]);

  const columns: Column<Center>[] = [
    {
      key: "name",
      header: "Centre",
      cell: (c) => (
        <div className="flex flex-col">
          <Link
            className="font-medium hover:underline"
            href={`/centers/${c.id}`}
          >
            {c.name}
          </Link>
          <span className="text-xs text-muted-foreground">{c.code}</span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (c) => <StatusBadge status={c.status} />,
    },
    {
      key: "timezone",
      header: "Timezone",
      secondary: true,
      cell: (c) => <span className="text-muted-foreground">{c.timezone}</span>,
    },
    {
      key: "collections",
      header: "Collections",
      align: "end",
      cell: (c) => (
        <span className="tabular-nums">
          {activity[c.id]?.transactions ?? "—"}
        </span>
      ),
    },
    {
      key: "quantity",
      header: "Quantity",
      align: "end",
      cell: (c) =>
        activity[c.id] ? (
          <Quantity value={activity[c.id].total_net_weight_kg} unit="kg" />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "value",
      header: "Value",
      align: "end",
      cell: (c) =>
        activity[c.id] ? (
          <Money
            amount={activity[c.id].payable_amount}
            currency={activity[c.id].currency}
          />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "last",
      header: "Last activity",
      secondary: true,
      cell: (c) => {
        const at = activity[c.id]?.last_collection_at;
        return (
          <span className="text-muted-foreground">
            {at ? at.slice(0, 10) : "no activity"}
          </span>
        );
      },
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "end",
      cell: (c) => (
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setForm({ mode: "edit", center: c })}
          >
            Edit
          </Button>
          {/* A link, styled as a button. This design system is Base UI, which
              has no `asChild`, so nesting an anchor inside <Button> would give
              a button that is not a link and does not navigate. */}
          <Link
            href={`/centers/${c.id}`}
            className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
          >
            Open
          </Link>
        </div>
      ),
    },
  ];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Collection centres"
        description="Where milk is received. Activity figures cover the last 30 days and are computed by the platform."
        actions={
          <Button type="button" onClick={() => setForm({ mode: "create" })}>
            <Plus aria-hidden className="me-1.5 size-4" />
            New centre
          </Button>
        }
      />

      <section
        aria-label="Centre summary"
        className="grid gap-4 sm:grid-cols-3"
      >
        <StatTile
          label="Centres"
          value={totals.centers}
          icon={<Building2 className="size-4" />}
        />
        <StatTile
          label="Active on this page"
          value={totals.active}
          hint="of the rows shown"
        />
        <StatTile
          label="Reporting activity"
          value={totals.reporting}
          hint="last 30 days"
        />
      </section>

      {form.mode !== "closed" ? (
        <CenterForm
          state={form}
          branches={branches}
          onClose={() => setForm({ mode: "closed" })}
          onSaved={() => {
            setForm({ mode: "closed" });
            void load();
          }}
        />
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <DataTable
            caption="Collection centres in this organization"
            columns={columns}
            rows={page?.items ?? []}
            rowKey={(c) => c.id}
            loading={loading}
            error={error}
            onRetry={() => void load()}
            empty={{
              title:
                q || status
                  ? "No centre matches this search"
                  : "No collection centres yet",
              description:
                q || status
                  ? "Try a different name, code or status."
                  : "A centre is where suppliers deliver milk. Create one to begin collecting.",
            }}
            toolbar={
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="center-search">Search</Label>
                  <div className="relative">
                    <Search
                      aria-hidden
                      className="pointer-events-none absolute left-2 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    />
                    <Input
                      id="center-search"
                      className="w-64 ps-8"
                      placeholder="Name or code"
                      value={q}
                      onChange={(e) => {
                        setQ(e.target.value);
                        setOffset(0);
                      }}
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="center-status">Status</Label>
                  <select
                    id="center-status"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
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
                  </select>
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
    </div>
  );
}

/**
 * Create and edit.
 *
 * Client validation exists to give a fast, specific message — never to decide
 * whether something is allowed. The platform's answer is authoritative and its
 * refusal is shown verbatim, because a form that invents its own reason will
 * eventually invent a wrong one.
 */
function CenterForm({
  state,
  branches,
  onClose,
  onSaved,
}: {
  state: Exclude<FormState, { mode: "closed" }>;
  branches: Branch[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const editing = state.mode === "edit";
  const [name, setName] = useState(editing ? state.center.name : "");
  const [code, setCode] = useState(editing ? state.center.code : "");
  const [timezone, setTimezone] = useState(
    editing ? state.center.timezone : "Africa/Nairobi",
  );
  const [branchId, setBranchId] = useState(branches[0]?.id ?? "");
  const [status, setStatus] = useState(
    editing ? state.center.status : "inactive",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const errors: Record<string, string> = {};
    if (name.trim().length < 2)
      errors.name = "Give the centre a name of at least 2 characters.";
    if (!editing && !/^[A-Za-z0-9-]{2,20}$/.test(code.trim()))
      errors.code =
        "A code is 2–20 letters, digits or hyphens, and cannot be changed later.";
    if (!TIMEZONE.test(timezone.trim()))
      errors.timezone = "Use an IANA timezone, for example Africa/Nairobi.";
    if (!editing && !branchId)
      errors.branch = "Choose the branch this centre belongs to.";
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
        await updateCenter(state.center.id, {
          name: name.trim(),
          timezone: timezone.trim(),
        });
        if (status !== state.center.status)
          await setCenterStatus(state.center.id, status);
      } else {
        await createCenter({
          branch_id: branchId,
          name: name.trim(),
          code: code.trim(),
        });
      }
      onSaved();
    } catch (err) {
      // The platform's own words. It knows rules this form does not.
      setError(
        err instanceof ApiError ? err.detail : "The centre could not be saved",
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
            {editing ? `Edit ${state.center.name}` : "New collection centre"}
          </h2>
          {error ? <ErrorState message={error} /> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              id="center-name"
              label="Name"
              required
              error={fieldErrors.name}
              hint="Shown wherever the centre appears."
            >
              <Input
                id="center-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-invalid={Boolean(fieldErrors.name)}
                placeholder="Kilima Hill Collection Centre"
              />
            </Field>

            <Field
              id="center-code"
              label="Code"
              required={!editing}
              error={fieldErrors.code}
              hint={
                editing
                  ? "A code cannot be changed after creation."
                  : "Short, unique, e.g. KH-C1."
              }
            >
              <Input
                id="center-code"
                value={code}
                disabled={editing}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                aria-invalid={Boolean(fieldErrors.code)}
                placeholder="KH-C1"
              />
            </Field>

            <Field
              id="center-timezone"
              label="Timezone"
              required
              error={fieldErrors.timezone}
              hint="Operating hours are interpreted in this zone."
            >
              <Input
                id="center-timezone"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                aria-invalid={Boolean(fieldErrors.timezone)}
                placeholder="Africa/Nairobi"
              />
            </Field>

            {editing ? (
              <Field id="center-status" label="Status">
                <select
                  id="center-status"
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  value={status}
                  onChange={(e) =>
                    setStatus(e.target.value as Center["status"])
                  }
                >
                  {["active", "inactive", "maintenance", "archived"].map(
                    (s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ),
                  )}
                </select>
              </Field>
            ) : (
              <Field
                id="center-branch"
                label="Branch"
                required
                error={fieldErrors.branch}
              >
                <select
                  id="center-branch"
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  value={branchId}
                  onChange={(e) => setBranchId(e.target.value)}
                  aria-invalid={Boolean(fieldErrors.branch)}
                >
                  <option value="">Select a branch…</option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            A new centre starts inactive and cannot receive milk until it is
            active, has operating hours, an assigned operator and a working
            scale. Its readiness page explains what is still missing.
          </p>

          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : editing ? "Save changes" : "Create centre"}
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

function Field({
  id,
  label,
  required,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        {required ? (
          <span aria-hidden className="ms-0.5 text-destructive">
            *
          </span>
        ) : null}
        {required ? <span className="sr-only"> (required)</span> : null}
      </Label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
