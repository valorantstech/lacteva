"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AdminPage } from "@/components/admin-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type Column, DataTable } from "@/components/data-table";
import {
  ApiError,
  type AuditPageResult,
  type AuditRecord,
  type Member,
  type User,
  listAudit,
  listAuditActions,
  listPeople,
} from "@/lib/api";

/**
 * The audit trail (PORTAL-001 / F-10, rebuilt in DEMO-007).
 *
 * This is the page an access review reads: SEC-003 made grants AND
 * revocations auditable precisely so that a trail with one and not the other
 * could not misrepresent who still holds what.
 *
 * Two things changed here, and both were correctness rather than polish:
 *
 * 1. THE FILTER IS THE DATABASE'S. It used to fetch the newest 200 records and
 *    filter them in the browser, so "find what this operator did to that
 *    settlement" quietly meant "…in the last 200 events". Now every filter is
 *    a query parameter and the count is the platform's `total`.
 *
 * 2. IT READS AS ENGLISH. `collection.transaction.WeightCaptured` on
 *    `milk_collection_transaction` is precise and unreadable. The action is
 *    split into what happened and what it happened to, the actor is resolved
 *    to a person's name, and the raw identifiers stay — smaller, underneath —
 *    because an auditor eventually needs them.
 */

const PAGE_SIZE = 25;

const describe = (e: unknown) => {
  if (e instanceof ApiError) return typeof e.extra === "string" && e.extra ? e.extra : e.detail;
  return e instanceof Error ? e.message : "Failed to load the audit trail";
};

const stamp = (iso: string) => String(iso).slice(0, 19).replace("T", " ");

/**
 * An action key, as English.
 *
 * The platform writes two shapes, and they need different handling:
 *
 *   `collection.transaction.WeightCaptured` → "Weight captured"
 *   `authz.role.granted`                    → "Role granted"
 *
 * The first already names its own subject, so the last segment is the whole
 * label. The second ends in a bare past participle, and "Granted" on its own
 * tells an auditor nothing — so the noun before it is kept. The test is
 * whether the final segment is CamelCase, which is how this codebase spells
 * an event name.
 */
function humanAction(action: string): string {
  const parts = action.split(".");
  const last = parts[parts.length - 1] ?? action;
  const isEventName = /^[A-Z]/.test(last);
  const words = isEventName ? [last] : parts.slice(-2);
  return words
    .join(" ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]/g, " ")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());
}

/**
 * The module path the action came from — `collection · transaction`. Kept as
 * secondary information so the precise key is still recoverable on screen.
 */
const areaOf = (action: string) => action.split(".").slice(0, -1).join(" · ") || "platform";

/** `milk_collection_transaction` → "Milk collection transaction". */
const humanResource = (t: string) =>
  t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/**
 * Where a record's resource can be opened. Only routes that exist — an audit
 * row for a table with no page must not become a dead link.
 */
function resourceHref(resourceType: string, id: string | null): string | null {
  if (!id) return null;
  switch (resourceType) {
    case "milk_collection_transaction":
      return `/transactions/${id}`;
    case "settlement":
      return `/settlements/${id}`;
    case "payment":
      return `/payments/${id}`;
    case "collection_center":
      return `/centers/${id}`;
    case "supplier":
      return `/suppliers/${id}`;
    default:
      return null;
  }
}

/**
 * The outcome, where the record carries one. Most audit entries record a fact
 * that succeeded — they are only written after the change — so the honest
 * default is "recorded", not a green tick implying a check was performed.
 */
function outcomeOf(record: AuditRecord): { label: string; tone: string } {
  const action = record.action.toLowerCase();
  const detail = record.detail ?? {};
  if (action.includes("failed") || action.includes("denied") || action.includes("rejected"))
    return { label: "failed", tone: "text-destructive" };
  if (action.includes("cancelled")) return { label: "cancelled", tone: "text-muted-foreground" };
  if (typeof detail.state === "string") return { label: String(detail.state), tone: "" };
  return { label: "recorded", tone: "text-muted-foreground" };
}

export default function AuditPage() {
  const [page, setPage] = useState<AuditPageResult | null>(null);
  const [actions, setActions] = useState<string[]>([]);
  const [people, setPeople] = useState<Array<Member & { user: User | null }>>([]);

  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filtered = Boolean(q || action || from || to);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listAudit({
          q: q || undefined,
          action: action || undefined,
          date_from: from || undefined,
          date_to: to || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      );
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, [action, from, offset, q, to]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 150);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    // The action vocabulary comes from this tenant's own history, and the
    // people list is the staff roster — both are fetched once, not per row.
    listAuditActions()
      .then(setActions)
      .catch(() => setActions([]));
    listPeople()
      .then(setPeople)
      .catch(() => setPeople([]));
  }, []);

  const actorName = useMemo(() => {
    const byId: Record<string, string> = {};
    for (const p of people) {
      if (p.user?.full_name) byId[p.user_id] = p.user.full_name;
      else if (p.user?.email) byId[p.user_id] = p.user.email;
    }
    return byId;
  }, [people]);

  const columns: Column<AuditRecord>[] = [
    {
      key: "when",
      header: "When",
      cell: (r) => <span className="tabular-nums text-sm">{stamp(r.created_at)}</span>,
    },
    {
      key: "actor",
      header: "Actor",
      cell: (r) =>
        r.actor_id ? (
          <div className="flex flex-col">
            <span>{actorName[r.actor_id] ?? "—"}</span>
            <span className="font-mono text-xs text-muted-foreground">
              {r.actor_id.slice(0, 8)}…
            </span>
          </div>
        ) : (
          <span className="text-muted-foreground">the platform</span>
        ),
    },
    {
      key: "action",
      header: "Action",
      cell: (r) => (
        <div className="flex flex-col">
          <span className="font-medium">{humanAction(r.action)}</span>
          <span className="text-xs text-muted-foreground">{areaOf(r.action)}</span>
        </div>
      ),
    },
    {
      key: "entity",
      header: "Entity",
      cell: (r) => {
        const href = resourceHref(r.resource_type, r.resource_id);
        const label = humanResource(r.resource_type);
        return (
          <div className="flex flex-col">
            {href ? (
              <Link className="hover:underline" href={href}>
                {label}
              </Link>
            ) : (
              <span>{label}</span>
            )}
            <span className="font-mono text-xs text-muted-foreground">
              {r.resource_id ? `${r.resource_id.slice(0, 8)}…` : "—"}
            </span>
          </div>
        );
      },
    },
    {
      key: "result",
      header: "Result",
      cell: (r) => {
        const { label, tone } = outcomeOf(r);
        return <span className={`text-sm ${tone}`}>{label}</span>;
      },
    },
  ];

  return (
    <AdminPage
      title="Audit trail"
      description="What was done, by whom, to what, and when. Newest first, append-only, and filtered by the platform rather than by this page."
    >
      <DataTable
        caption="Audit records for this organization"
        columns={columns}
        rows={page?.items ?? []}
        rowKey={(r) => r.id}
        loading={loading}
        error={error}
        onRetry={() => void load()}
        empty={{
          title: filtered ? "No record matches these filters" : "No recorded activity yet",
          description: filtered
            ? "Try a wider date range, or clear the filters."
            : "Every change made through the platform is recorded here.",
        }}
        toolbar={
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="au-q">Search</Label>
              <Input
                id="au-q"
                className="h-9 w-56"
                placeholder="Action, entity or id"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setOffset(0);
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="au-action">Action</Label>
              <select
                id="au-action"
                className="h-9 max-w-64 rounded-md border border-input bg-background px-2 text-sm"
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All actions</option>
                {actions.map((a) => (
                  <option key={a} value={a}>
                    {humanAction(a)} ({areaOf(a)})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="au-from">From</Label>
              <Input
                id="au-from"
                type="date"
                className="h-9"
                value={from}
                onChange={(e) => {
                  setFrom(e.target.value);
                  setOffset(0);
                }}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="au-to">To</Label>
              <Input
                id="au-to"
                type="date"
                className="h-9"
                value={to}
                onChange={(e) => {
                  setTo(e.target.value);
                  setOffset(0);
                }}
              />
            </div>
            {filtered ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setQ("");
                  setAction("");
                  setFrom("");
                  setTo("");
                  setOffset(0);
                }}
              >
                Clear filters
              </Button>
            ) : null}
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
    </AdminPage>
  );
}
