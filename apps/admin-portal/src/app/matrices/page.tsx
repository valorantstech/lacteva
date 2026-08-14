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
  MatrixDetail,
  MatrixPage,
  MatrixRow,
  PricingMatrix,
  QualityDimension,
  RateCard,
  createMatrix,
  createMatrixRow,
  deleteMatrix,
  deleteMatrixRow,
  getMatrixDetail,
  listMatrices,
  listQualityDimensions,
  listRateCards,
  updateMatrixRow,
} from "@/lib/api";

const PAGE_SIZE = 10;
const STATUSES = ["", "draft", "active", "archived"] as const;

const statusVariant = (s: PricingMatrix["status"]) =>
  s === "active" ? "default" : s === "archived" ? "outline" : "secondary";

export default function MatricesPage() {
  const [page, setPage] = useState<MatrixPage | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<MatrixDetail | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPage(await listMatrices({ q, status, limit: PAGE_SIZE, offset }));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load matrices");
    }
  }, [q, status, offset]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 150);
    return () => clearTimeout(t);
  }, [refresh]);

  async function openDetail(id: string) {
    try {
      setDetail(await getMatrixDetail(id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load matrix");
    }
  }

  async function removeMatrix(m: PricingMatrix) {
    try {
      await deleteMatrix(m.id);
      if (detail?.matrix.id === m.id) setDetail(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Delete failed");
    }
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pricing matrices</h1>
          <p className="text-sm text-muted-foreground">
            Quality-banded price definitions per rate card and product — data only, no
            calculations yet
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>New matrix</Button>
      </header>

      <div className="flex gap-3">
        <Input
          placeholder="Search name or product…"
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

      {showCreate && (
        <MatrixCreateForm
          onDone={async () => {
            setShowCreate(false);
            await refresh();
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Rate card</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>Dimension</TableHead>
                <TableHead>Bands</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-end">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page?.items.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.name}</TableCell>
                  <TableCell className="font-mono">
                    {m.rate_card_code} v{m.version}
                  </TableCell>
                  <TableCell>{m.product_name || m.product_code}</TableCell>
                  <TableCell className="font-mono">{m.dimension_code}</TableCell>
                  <TableCell>{m.row_count}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(m.status)}>{m.status}</Badge>
                  </TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => openDetail(m.id)}>
                      Detail
                    </Button>
                    {m.status === "draft" && (
                      <Button size="sm" variant="ghost" onClick={() => removeMatrix(m)}>
                        Delete
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {page && page.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No pricing matrices match.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {detail && (
        <MatrixDetailCard
          detail={detail}
          onRefresh={async () => {
            await openDetail(detail.matrix.id);
            await refresh();
          }}
          onClose={() => setDetail(null)}
          onError={setError}
        />
      )}

      <footer className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {page ? `${page.total} matri${page.total === 1 ? "x" : "ces"}` : "Loading…"}
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

function MatrixDetailCard({
  detail,
  onRefresh,
  onClose,
  onError,
}: {
  detail: MatrixDetail;
  onRefresh: () => Promise<void>;
  onClose: () => void;
  onError: (e: string) => void;
}) {
  const { matrix, dimension, rows, gaps, editable } = detail;

  async function saveRow(row: MatrixRow, patch: Partial<MatrixRow>) {
    try {
      await updateMatrixRow(matrix.id, row.id, {
        from_value: patch.from_value ?? row.from_value,
        to_value: patch.to_value ?? row.to_value,
        unit_price: patch.unit_price ?? row.unit_price,
        active: patch.active ?? row.active,
      });
      await onRefresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "Row update failed");
    }
  }

  async function removeRow(row: MatrixRow) {
    try {
      await deleteMatrixRow(matrix.id, row.id);
      await onRefresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "Row delete failed");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          {matrix.name}
          <Badge variant={statusVariant(matrix.status)}>{matrix.status}</Badge>
        </CardTitle>
        <CardDescription>
          {matrix.rate_card_code} v{matrix.version} · {matrix.product_name || matrix.product_code}{" "}
          · {dimension.name} ({dimension.code}
          {dimension.unit ? `, ${dimension.unit}` : ""}
          {dimension.min_value !== null && dimension.max_value !== null
            ? `, ${dimension.min_value}–${dimension.max_value}`
            : ""}
          )
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>From</TableHead>
              <TableHead>To (excl.)</TableHead>
              <TableHead>Unit price</TableHead>
              <TableHead>Active</TableHead>
              {editable && <TableHead className="text-end">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) =>
              editable ? (
                <EditableRow key={r.id} row={r} onSave={saveRow} onDelete={removeRow} />
              ) : (
                <TableRow key={r.id} className={r.active ? "" : "opacity-50"}>
                  <TableCell>{r.from_value}</TableCell>
                  <TableCell>{r.to_value}</TableCell>
                  <TableCell>{r.unit_price}</TableCell>
                  <TableCell>{r.active ? "yes" : "no"}</TableCell>
                </TableRow>
              ),
            )}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No price bands yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        {gaps.length > 0 && (
          <p className="text-amber-600 dark:text-amber-500">
            Continuity gaps:{" "}
            {gaps.map((g) => `[${g.from_value} – ${g.to_value})`).join(", ")}
          </p>
        )}

        {editable ? (
          <NewRowForm
            matrixId={matrix.id}
            onDone={onRefresh}
            onError={onError}
          />
        ) : (
          <p className="text-muted-foreground">
            Read-only — this matrix follows its rate card and is no longer draft.
          </p>
        )}
        <div>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function EditableRow({
  row,
  onSave,
  onDelete,
}: {
  row: MatrixRow;
  onSave: (row: MatrixRow, patch: Partial<MatrixRow>) => Promise<void>;
  onDelete: (row: MatrixRow) => Promise<void>;
}) {
  const [from, setFrom] = useState(String(row.from_value));
  const [to, setTo] = useState(String(row.to_value));
  const [price, setPrice] = useState(String(row.unit_price));

  return (
    <TableRow className={row.active ? "" : "opacity-50"}>
      <TableCell>
        <Input className="h-7 w-24" value={from} onChange={(e) => setFrom(e.target.value)} />
      </TableCell>
      <TableCell>
        <Input className="h-7 w-24" value={to} onChange={(e) => setTo(e.target.value)} />
      </TableCell>
      <TableCell>
        <Input className="h-7 w-28" value={price} onChange={(e) => setPrice(e.target.value)} />
      </TableCell>
      <TableCell>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onSave(row, { active: !row.active })}
        >
          {row.active ? "yes" : "no"}
        </Button>
      </TableCell>
      <TableCell className="flex justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            onSave(row, {
              from_value: Number(from),
              to_value: Number(to),
              unit_price: Number(price),
            })
          }
        >
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onDelete(row)}>
          Delete
        </Button>
      </TableCell>
    </TableRow>
  );
}

function NewRowForm({
  matrixId,
  onDone,
  onError,
}: {
  matrixId: string;
  onDone: () => Promise<void>;
  onError: (e: string) => void;
}) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      await createMatrixRow(matrixId, {
        from_value: Number(from),
        to_value: Number(to),
        unit_price: Number(price),
      });
      setFrom("");
      setTo("");
      setPrice("");
      await onDone();
    } catch (err) {
      onError(err instanceof ApiError ? err.detail : "Row create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-end gap-2">
      <div className="flex flex-col gap-1">
        <Label>From</Label>
        <Input className="h-8 w-24" value={from} onChange={(e) => setFrom(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label>To (excl.)</Label>
        <Input className="h-8 w-24" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label>Unit price</Label>
        <Input className="h-8 w-28" value={price} onChange={(e) => setPrice(e.target.value)} />
      </div>
      <Button size="sm" disabled={busy || !from || !to || !price} onClick={add}>
        Add band
      </Button>
    </div>
  );
}

function MatrixCreateForm({
  onDone,
  onCancel,
}: {
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [cards, setCards] = useState<RateCard[]>([]);
  const [dimensions, setDimensions] = useState<QualityDimension[]>([]);
  const [rateCardId, setRateCardId] = useState("");
  const [name, setName] = useState("");
  const [productCode, setProductCode] = useState("");
  const [productName, setProductName] = useState("");
  const [dimensionCode, setDimensionCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      listRateCards({ status: "draft", limit: 100, offset: 0 })
        .then((p) => setCards(p.items))
        .catch(() => setCards([]));
      listQualityDimensions()
        .then(setDimensions)
        .catch(() => setDimensions([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createMatrix({
        rate_card_id: rateCardId,
        name,
        product_code: productCode,
        product_name: productName,
        dimension_code: dimensionCode,
      });
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New pricing matrix</CardTitle>
        <CardDescription>
          Matrices attach to a draft rate card; the product must be in the card&apos;s scope.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid max-w-2xl grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="m-card">Rate card (draft)</Label>
            <select
              id="m-card"
              required
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              value={rateCardId}
              onChange={(e) => setRateCardId(e.target.value)}
            >
              <option value="">Select…</option>
              {cards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} v{c.version} — {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="m-name">Name</Label>
            <Input
              id="m-name"
              required
              minLength={2}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="m-product">Product code</Label>
            <Input
              id="m-product"
              required
              placeholder="e.g. RAW-COW-MILK"
              value={productCode}
              onChange={(e) => setProductCode(e.target.value.toUpperCase())}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="m-product-name">Product name (optional)</Label>
            <Input
              id="m-product-name"
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="m-dimension">Quality dimension</Label>
            <select
              id="m-dimension"
              required
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
              value={dimensionCode}
              onChange={(e) => setDimensionCode(e.target.value)}
            >
              <option value="">Select…</option>
              {dimensions
                .filter((d) => d.active)
                .map((d) => (
                  <option key={d.id} value={d.code}>
                    {d.code} — {d.name}
                  </option>
                ))}
            </select>
          </div>
          {error && <p className="col-span-2 text-sm text-destructive">{error}</p>}
          <div className="col-span-2 flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create"}
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
