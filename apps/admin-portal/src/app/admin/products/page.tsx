"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { ScrollHint } from "@/components/scroll-hint";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/money";
import {
  type Product,
  type Session,
  can,
  createProduct,
  describeError,
  getSession,
  listProducts,
  updateProduct,
} from "@/lib/api";

/**
 * The catalogue (WO-81 · LACTEVA-SALES-001).
 *
 * What the organisation sells — the morning milk on a standing order AND the
 * dahi, the shrikhand, the sweets a household takes beside it. One list: a
 * standing order names a product from it, an item sold at the door names a
 * product from it, and a bill prints the product's NAME from it.
 *
 * Two things this page says plainly, because both are the kind of fact that
 * gets discovered by a wrong bill:
 *
 *  * the default price is a SUGGESTION. It prefills a form and prices an
 *    item recorded without a price. It never touches a standing order's
 *    rate — that belongs to the household, on their plan;
 *  * a product is deactivated, never deleted. A product on an issued bill
 *    must keep resolving to its name for as long as the bill exists.
 */
/** WO-107 §5: SUGGESTIONS. A shop sells packets, boxes, bottles, dozens,
 *  grams — the unit is the label the customer sees on the bill (1–12
 *  characters), and quantity × rate is the arithmetic whatever it says. */
const UNITS = ["pc", "L", "kg"] as const;

export default function ProductsPage() {
  const [session, setSession] = useState<Session | null>(null);
  const [page, setPage] = useState<Product[] | null>(null);
  const [showRetired, setShowRetired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [editing, setEditing] = useState<Product | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const result = await listProducts(showRetired ? null : true);
      setPage(result.items);
    } catch (err) {
      setError(describeError(err, "Could not load the catalogue"));
    }
  }, [showRetired]);

  useEffect(() => {
    getSession().then(setSession).catch(() => setSession(null));
  }, []);
  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  const mayManage = can(session, "catalog.manage");

  return (
    <AdminPage
      title="Products"
      description="What this organisation sells. Milk sold by standing order is a product too and must be here; so is anything sold beside it — dahi, sweets, a cold drink. The default price only prefills a form and prices an item recorded without one; a household's own rate on its standing order always wins."
      error={error}
      note={note}
    >
      {mayManage ? (
        <NewProductForm
          onDone={(message) => {
            setNote(message);
            void load();
          }}
        />
      ) : null}

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showRetired}
            onChange={(e) => setShowRetired(e.target.checked)}
          />
          Show deactivated products
        </label>
      </div>

      {page === null ? (
        <p className="text-sm text-muted-foreground">Loading the catalogue…</p>
      ) : page.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing here yet. Add the milk you deliver and anything else you sell.
        </p>
      ) : (
        <ScrollHint>
          <table className="w-full text-sm">
            <caption className="sr-only">Products in the catalogue</caption>
            <thead>
              <tr className="border-b text-start text-muted-foreground">
                <th className="py-2 pe-4 font-medium">Code</th>
                <th className="py-2 pe-4 font-medium">Name</th>
                <th className="py-2 pe-4 font-medium">Unit</th>
                <th className="py-2 pe-4 text-end font-medium">Default price</th>
                <th className="py-2 pe-4 font-medium">Status</th>
                {mayManage ? <th className="py-2 font-medium" /> : null}
              </tr>
            </thead>
            <tbody>
              {page.map((product) => (
                <tr key={product.id} className="border-b last:border-0">
                  <td className="py-2 pe-4 font-mono text-xs">{product.code}</td>
                  <td className="py-2 pe-4">{product.name}</td>
                  <td className="py-2 pe-4 text-muted-foreground">{product.unit}</td>
                  <td className="py-2 pe-4 text-end tabular-nums">
                    {product.default_price === null ? (
                      <span className="text-muted-foreground">no price</span>
                    ) : (
                      <Money amount={product.default_price} currency={product.currency} />
                    )}
                  </td>
                  <td className="py-2 pe-4">
                    {product.active ? (
                      "active"
                    ) : (
                      <span className="text-muted-foreground">deactivated</span>
                    )}
                  </td>
                  {mayManage ? (
                    <td className="py-2 text-end">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditing(product)}
                      >
                        Edit
                      </Button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollHint>
      )}

      {editing ? (
        <EditProductForm
          product={editing}
          onCancel={() => setEditing(null)}
          onDone={(message) => {
            setEditing(null);
            setNote(message);
            void load();
          }}
        />
      ) : null}
    </AdminPage>
  );
}

function NewProductForm({ onDone }: { onDone: (message: string) => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [unit, setUnit] = useState<string>("pc");
  const [price, setPrice] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-lg border border-border p-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setWorking(true);
        setError(null);
        try {
          // WO-107 §3: the code is the platform's to spell unless the owner
          // cares; blank means "generate it from the name".
          const created = await createProduct({
            ...(code.trim() ? { code: code.trim() } : {}),
            name,
            unit: unit.trim(),
            ...(price.trim() ? { default_price: price.trim() } : {}),
          });
          setCode("");
          setName("");
          setPrice("");
          onDone(`Added ${created.name} (${created.code}).`);
        } catch (err) {
          setError(describeError(err, "The platform refused the product"));
        } finally {
          setWorking(false);
        }
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-name">Name</Label>
        <Input
          id="p-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Dahi 500 g"
          className="min-w-56"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-unit">Unit</Label>
        <Input
          id="p-unit"
          list="p-unit-suggestions"
          value={unit}
          maxLength={12}
          onChange={(e) => setUnit(e.target.value)}
          placeholder="pc, L, kg, packet…"
          className="w-32"
        />
        <datalist id="p-unit-suggestions">
          {UNITS.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="p-price">Default price (optional)</Label>
        <Input
          id="p-price"
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="40.00"
          className="w-32"
        />
      </div>
      <Button type="submit" disabled={working || !name.trim() || !unit.trim()}>
        {working ? "Adding…" : "Add product"}
      </Button>
      {/* WO-107 §3: codes are not the owner's job. Generated from the name
          unless somebody who cares types one here. */}
      <details className="basis-full">
        <summary className="cursor-pointer text-xs text-muted-foreground">More options</summary>
        <div className="mt-2 flex flex-col gap-1.5">
          <Label htmlFor="p-code">Code (optional — generated from the name)</Label>
          <Input
            id="p-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="DAHI-500G"
            className="w-48 font-mono"
          />
        </div>
      </details>
      {error ? (
        <p role="alert" className="w-full text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </form>
  );
}

function EditProductForm({
  product,
  onCancel,
  onDone,
}: {
  product: Product;
  onCancel: () => void;
  onDone: (message: string) => void;
}) {
  const [name, setName] = useState(product.name);
  const [unit, setUnit] = useState(product.unit);
  const [price, setPrice] = useState(
    product.default_price === null ? "" : String(product.default_price),
  );
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(active?: boolean) {
    setWorking(true);
    setError(null);
    try {
      const trimmed = price.trim();
      const updated = await updateProduct(product.id, {
        name,
        unit,
        ...(trimmed ? { default_price: trimmed } : { clear_default_price: true }),
        ...(active === undefined ? {} : { active }),
      });
      onDone(
        active === false
          ? `${updated.name} is deactivated. It stays on every bill it is already on.`
          : `Saved ${updated.name}.`,
      );
    } catch (err) {
      setError(describeError(err, "The platform refused the change"));
    } finally {
      setWorking(false);
    }
  }

  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-lg border border-border p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p className="w-full text-sm">
        Editing <span className="font-mono text-xs">{product.code}</span>. The code
        cannot change — every standing order and bill line names it.
      </p>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="e-name">Name</Label>
        <Input id="e-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="e-unit">Unit</Label>
        <Select id="e-unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
          {UNITS.map((u) => (
            <option key={u} value={u}>
              {u}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="e-price">Default price</Label>
        <Input
          id="e-price"
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="leave empty for no price"
          className="w-40"
        />
      </div>
      <Button type="submit" disabled={working}>
        {working ? "Saving…" : "Save"}
      </Button>
      {product.active ? (
        <Button
          type="button"
          variant="outline"
          disabled={working}
          onClick={() => void save(false)}
        >
          Deactivate
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          disabled={working}
          onClick={() => void save(true)}
        >
          Reactivate
        </Button>
      )}
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
      {error ? (
        <p role="alert" className="w-full text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </form>
  );
}
