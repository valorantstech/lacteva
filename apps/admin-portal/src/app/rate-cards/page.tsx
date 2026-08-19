"use client";

import Link from "next/link";

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
import { useLocale } from "@/lib/i18n";
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
  RateCard,
  RateCardDetail,
  RateCardPage,
  assignRateCardCenter,
  assignRateCardProduct,
  createRateCard,
  getRateCardDetail,
  listBranches,
  listCenters,
  listRateCards,
  rateCardAction,
  updateRateCard,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = [
  "",
  "draft",
  "under_review",
  "approved",
  "published",
  "archived",
] as const;

const statusVariant = (s: RateCard["status"]) =>
  s === "published" ? "default" : s === "archived" ? "outline" : "secondary";

const statusLabel = (s: string) => s.replace("_", " ");

// Workflow actions available per status (published is immutable; archived terminal).
const ACTIONS: Record<RateCard["status"], { label: string; action: string }[]> =
  {
    draft: [
      { label: "Submit", action: "submit" },
      { label: "Archive", action: "archive" },
    ],
    under_review: [
      { label: "Approve", action: "approve" },
      { label: "Archive", action: "archive" },
    ],
    approved: [
      { label: "Publish", action: "publish" },
      { label: "Archive", action: "archive" },
    ],
    published: [
      { label: "New version", action: "versions" },
      { label: "Archive", action: "archive" },
    ],
    archived: [{ label: "New version", action: "versions" }],
  };

type FormState =
  { mode: "closed" } | { mode: "create" } | { mode: "edit"; card: RateCard };

export default function RateCardsPage() {
  const [page, setPage] = useState<RateCardPage | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [centers, setCenters] = useState<Center[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [currency, setCurrency] = useState("");
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<FormState>({ mode: "closed" });
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<RateCardDetail | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPage(
        await listRateCards({ q, status, currency, limit: PAGE_SIZE, offset }),
      );
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to load rate cards",
      );
    }
  }, [q, status, currency, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      listBranches()
        .then(setBranches)
        .catch(() => setBranches([]));
      listCenters({ limit: 100, offset: 0 })
        .then((p) => setCenters(p.items))
        .catch(() => setCenters([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  async function openDetail(card: RateCard) {
    try {
      setDetail(await getRateCardDetail(card.id));
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to load rate card",
      );
    }
  }

  // P1-PORTAL-SCALE-001 (audit D-11): publishing decides what every farmer
  // on the card is paid, and archiving takes a card out of use — both were a
  // single click. They now ask, in the same words the settlement finalize
  // panel uses. The backend stays the authority: this is a pause, not a
  // security boundary.
  const [confirmAction, setConfirmAction] = useState<{
    card: RateCard;
    action: "publish" | "archive";
  } | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  async function runAction(card: RateCard, action: string) {
    setActionBusy(true);
    try {
      await rateCardAction(card.id, action);
      setError(null);
      setConfirmAction(null);
      await refresh();
      if (detail?.card.id === card.id)
        setDetail(await getRateCardDetail(card.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setActionBusy(false);
    }
  }

  function requestAction(card: RateCard, action: string) {
    if (action === "publish" || action === "archive") {
      setConfirmAction({ card, action });
      return;
    }
    void runAction(card, action);
  }

  async function assignCenter(cardId: string, centerId: string) {
    try {
      await assignRateCardCenter(cardId, centerId);
      setDetail(await getRateCardDetail(cardId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Assignment failed");
    }
  }

  async function assignProduct(cardId: string, code: string) {
    try {
      await assignRateCardProduct(cardId, code);
      setDetail(await getRateCardDetail(cardId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Assignment failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Rate cards</h1>
          <p className="text-sm text-muted-foreground">
            Pricing agreements per collection center and product — lifecycle
            only, no calculations yet
          </p>
        </div>
        <Button onClick={() => setForm({ mode: "create" })}>
          New rate card
        </Button>
      </header>

      <div className="flex gap-3">
        <Input
          placeholder="Search code or name…"
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
              {s === "" ? "All statuses" : statusLabel(s)}
            </option>
          ))}
        </select>
        <Input
          placeholder="Currency (e.g. KES)"
          value={currency}
          maxLength={3}
          onChange={(e) => {
            setCurrency(e.target.value);
            setOffset(0);
          }}
          className="max-w-28"
        />
      </div>

      {confirmAction ? (
        <div className="flex flex-col gap-3 rounded-md border border-destructive/40 bg-destructive/5 p-4">
          <p className="text-sm font-medium">
            {confirmAction.action === "publish"
              ? `Publishing ${confirmAction.card.code} v${confirmAction.card.version} is permanent: the card becomes immutable, and from its effective date it decides what every farmer priced by it is paid. A correction after this is a new version, never an edit.`
              : `Archiving ${confirmAction.card.code} v${confirmAction.card.version} takes it out of use — it prices no new collections afterwards.`}
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="destructive"
              disabled={actionBusy}
              onClick={() =>
                void runAction(confirmAction.card, confirmAction.action)
              }
            >
              {actionBusy
                ? "Working…"
                : confirmAction.action === "publish"
                  ? "Yes, publish permanently"
                  : "Yes, archive it"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={actionBusy}
              onClick={() => setConfirmAction(null)}
            >
              Keep it as it is
            </Button>
          </div>
        </div>
      ) : null}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {form.mode !== "closed" && (
        <RateCardForm
          branches={branches}
          card={form.mode === "edit" ? form.card : null}
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
                <TableHead>Currency</TableHead>
                <TableHead>Effective</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-end">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono">{c.code}</TableCell>
                  <TableCell>{c.name}</TableCell>
                  <TableCell>{c.currency}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    {c.effective_from} → {c.effective_until ?? "open"}
                  </TableCell>
                  <TableCell>v{c.version}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(c.status)}>
                      {statusLabel(c.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    {/* DEMO-004: the bands live on their own page now. */}
                    <Link
                      href={`/rate-cards/${c.id}`}
                      className="inline-flex h-8 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
                    >
                      Bands
                    </Link>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openDetail(c)}
                    >
                      Detail
                    </Button>
                    {c.status === "draft" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setForm({ mode: "edit", card: c })}
                      >
                        Edit
                      </Button>
                    )}
                    {ACTIONS[c.status].map((a) => (
                      <Button
                        key={a.action}
                        size="sm"
                        variant={a.action === "archive" ? "ghost" : "outline"}
                        onClick={() => requestAction(c, a.action)}
                      >
                        {a.label}
                      </Button>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center text-muted-foreground"
                  >
                    No rate cards match.
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
              {detail.card.name}
              <Badge variant={statusVariant(detail.card.status)}>
                {statusLabel(detail.card.status)}
              </Badge>
            </CardTitle>
            <CardDescription>
              {detail.card.code} v{detail.card.version} · {detail.card.currency}{" "}
              · {detail.card.effective_from} →{" "}
              {detail.card.effective_until ?? "open-ended"}
              {detail.card.published_at &&
                ` · published ${detail.card.published_at.slice(0, 10)}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            {detail.card.description && <p>{detail.card.description}</p>}
            <div>
              <span className="font-medium">Collection centers:</span>{" "}
              {detail.center_ids.length === 0
                ? "none — required before publishing"
                : centers
                    .filter((c) => detail.center_ids.includes(c.id))
                    .map((c) => c.code)
                    .join(" · ") || `${detail.center_ids.length} assigned`}
            </div>
            <div>
              <span className="font-medium">Products:</span>{" "}
              {detail.products.length === 0
                ? "none — required before publishing"
                : detail.products
                    .map((p) => p.product_name || p.product_code)
                    .join(" · ")}
            </div>
            {detail.card.status === "draft" && (
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                  defaultValue=""
                  id="rc-assign-center"
                >
                  <option value="" disabled>
                    Assign to center…
                  </option>
                  {centers
                    .filter((c) => !detail.center_ids.includes(c.id))
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
                    const el = document.getElementById(
                      "rc-assign-center",
                    ) as HTMLSelectElement;
                    if (el?.value) void assignCenter(detail.card.id, el.value);
                  }}
                >
                  Assign center
                </Button>
                <Input
                  id="rc-assign-product"
                  placeholder="Product code"
                  className="max-w-40"
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const el = document.getElementById(
                      "rc-assign-product",
                    ) as HTMLInputElement;
                    if (el?.value) void assignProduct(detail.card.id, el.value);
                  }}
                >
                  Add product
                </Button>
              </div>
            )}
            <p className="text-muted-foreground">
              Pricing rules: none — rate tables arrive with Increment-002.
            </p>
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
          {page
            ? `${page.total} rate card${page.total === 1 ? "" : "s"}`
            : "Loading…"}
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

function RateCardForm({
  branches,
  card,
  onDone,
  onCancel,
}: {
  branches: Branch[];
  card: RateCard | null;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(card?.name ?? "");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState(card?.description ?? "");
  // DEMO-013: a new rate card starts in the ORGANIZATION's currency.
  const { currency: orgCurrency } = useLocale();
  const [currency, setCurrency] = useState(card?.currency ?? orgCurrency ?? "");
  const [effectiveFrom, setEffectiveFrom] = useState(
    card?.effective_from ?? "",
  );
  const [effectiveUntil, setEffectiveUntil] = useState(
    card?.effective_until ?? "",
  );
  const [branchId, setBranchId] = useState(card?.branch_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name,
      description,
      currency,
      effective_from: effectiveFrom,
      effective_until: effectiveUntil || null,
      branch_id: branchId || null,
    };
    try {
      if (card) await updateRateCard(card.id, body);
      else await createRateCard(code ? { ...body, code } : body);
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
        <CardTitle>
          {card ? `Edit ${card.code} v${card.version}` : "New rate card"}
        </CardTitle>
        <CardDescription>
          Rate cards start as drafts; publishing requires review, approval, and
          at least one center and product assignment.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid max-w-2xl grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-name">Name</Label>
            <Input
              id="rc-name"
              required
              minLength={2}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          {!card && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rc-code">Code (optional)</Label>
              <Input
                id="rc-code"
                value={code}
                placeholder="Generated if empty"
                onChange={(e) => setCode(e.target.value.toUpperCase())}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-currency">Currency</Label>
            <Input
              id="rc-currency"
              required
              minLength={3}
              maxLength={3}
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-from">Effective from</Label>
            <Input
              id="rc-from"
              type="date"
              required
              value={effectiveFrom}
              onChange={(e) => setEffectiveFrom(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-until">Effective until (optional)</Label>
            <Input
              id="rc-until"
              type="date"
              value={effectiveUntil ?? ""}
              onChange={(e) => setEffectiveUntil(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rc-branch">Branch (optional)</Label>
            <select
              id="rc-branch"
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              value={branchId ?? ""}
              onChange={(e) => setBranchId(e.target.value)}
            >
              <option value="">Whole organization</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.code} — {b.name}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <Label htmlFor="rc-description">Description</Label>
            <Input
              id="rc-description"
              value={description}
              maxLength={500}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {error && (
            <p className="col-span-2 text-sm text-destructive">{error}</p>
          )}
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
