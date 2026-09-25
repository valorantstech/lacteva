"use client";

import { useEffect, useState } from "react";
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
import { Select } from "@/components/ui/select";
import { useBusinessToday } from "@/components/date-range";
import {
  type Product,
  type RateChangeResult,
  changeCustomerRates,
  describeError,
  listCustomers,
  listProducts,
} from "@/lib/api";

/**
 * Change the rate for many households at once (WO-89 §5).
 *
 * A rate rise applied by opening four hundred customer records is not a
 * feature anybody will use. This card names a product, a new rate and the
 * date it applies from, for everyone holding an active plan for that product
 * or for a list of customer codes — then PREVIEWS: how many plans would be
 * superseded, what their old rates were, and who would be skipped and why (a
 * paused plan, an inactive customer, a plan already at that rate). Nothing
 * is touched until the preview is confirmed; the platform then applies it in
 * one transaction and reports the same list back.
 *
 * Deliveries already recorded keep the rate they were recorded at — a rate
 * from the 1st changes what the 2nd costs and nothing about the 31st before
 * it. That is the platform's rule (the plan supersedes, the delivery copies)
 * and the card says so where the owner is about to press the button.
 */
export function RateChangeCard({
  onClose,
  onApplied,
}: {
  onClose: () => void;
  onApplied?: (message: string) => void;
}) {
  const today = useBusinessToday();
  const [products, setProducts] = useState<Product[]>([]);
  const [product, setProduct] = useState("");
  const [rate, setRate] = useState("");
  const [from, setFrom] = useState("");
  const [scope, setScope] = useState<"everyone" | "codes">("everyone");
  const [codes, setCodes] = useState("");
  const [preview, setPreview] = useState<RateChangeResult | null>(null);
  const [result, setResult] = useState<RateChangeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      listProducts()
        .then((p) => {
          const items = p.items ?? [];
          setProducts(items);
        })
        .catch(() => setProducts([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  const effectiveFrom = from || today || undefined;

  async function resolveSelection(): Promise<string[] | null> {
    if (scope === "everyone") return null;
    const wanted = codes
      .split(/[\s,;]+/)
      .map((c) => c.trim())
      .filter(Boolean);
    if (wanted.length === 0) throw new Error("Enter at least one customer code, or choose everyone.");
    const ids: string[] = [];
    const missing: string[] = [];
    for (const code of wanted) {
      const page = await listCustomers({ q: code, limit: 5, offset: 0 });
      const hit = page.items.find((c) => c.code === code);
      if (hit) ids.push(hit.id);
      else missing.push(code);
    }
    if (missing.length) throw new Error(`No customer with code ${missing.join(", ")}.`);
    return ids;
  }

  async function run(confirm: boolean) {
    setBusy(true);
    setError(null);
    try {
      const customer_ids = await resolveSelection();
      const answer = await changeCustomerRates({
        product,
        unit_price: rate.trim(),
        effective_from: effectiveFrom,
        customer_ids,
        preview: !confirm,
      });
      if (confirm) {
        setResult(answer);
        setPreview(null);
        onApplied?.(
          `Rate changed to ${String(answer.unit_price)} for ${answer.changed.length} plan(s) from ${answer.effective_from}; ${answer.skipped.length} skipped.`,
        );
      } else {
        setPreview(answer);
        setResult(null);
      }
    } catch (err) {
      setError(err instanceof Error && !("status" in err) ? err.message : describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const shown = result ?? preview;

  return (
    <Card data-testid="rate-change-card">
      <CardHeader>
        <CardTitle className="text-base">Change rate</CardTitle>
        <CardDescription>
          A new rate for one product, for everyone holding a standing order for it
          or for the customers you name, from a date. Each household&apos;s plan is
          superseded — never edited — so what was delivered before the date keeps
          the rate it was recorded at. You see exactly what will change before
          anything does.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form
          className="grid gap-3 sm:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(false);
          }}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="rate-product">Product</Label>
            <Select
              id="rate-product"
              required
              value={product}
              onChange={(e) => {
                setProduct(e.target.value);
                setPreview(null);
              }}
            >
              <option value="">Choose…</option>
              {products.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="rate-price">New rate</Label>
            <Input
              id="rate-price"
              required
              inputMode="decimal"
              value={rate}
              onChange={(e) => {
                setRate(e.target.value);
                setPreview(null);
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="rate-from">From</Label>
            <Input
              id="rate-from"
              type="date"
              value={from || today || ""}
              onChange={(e) => {
                setFrom(e.target.value);
                setPreview(null);
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="rate-scope">Who</Label>
            <Select
              id="rate-scope"
              value={scope}
              onChange={(e) => {
                setScope(e.target.value as "everyone" | "codes");
                setPreview(null);
              }}
            >
              <option value="everyone">Everyone with an active plan for it</option>
              <option value="codes">Only these customer codes</option>
            </Select>
          </div>
          {scope === "codes" ? (
            <div className="flex flex-col gap-1 sm:col-span-4">
              <Label htmlFor="rate-codes">Customer codes, separated by commas or lines</Label>
              <textarea
                id="rate-codes"
                className="min-h-16 rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={codes}
                onChange={(e) => {
                  setCodes(e.target.value);
                  setPreview(null);
                }}
              />
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 sm:col-span-4">
            <Button type="submit" size="sm" variant="outline" disabled={busy || !product || !rate.trim()}>
              Preview
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={onClose}>
              Close
            </Button>
          </div>
        </form>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            The platform refused: {error}
          </p>
        ) : null}

        {shown ? (
          <div className="flex flex-col gap-3" data-testid="rate-change-preview">
            <p className="text-sm">
              {shown.preview ? "Would change" : "Changed"}{" "}
              <strong>{shown.changed.length}</strong> plan(s) to {String(shown.unit_price)} from{" "}
              {shown.effective_from}
              {shown.skipped.length ? `; ${shown.skipped.length} skipped` : ""}.
            </p>
            {shown.changed.length ? (
              <ul className="max-h-48 overflow-y-auto text-xs text-muted-foreground">
                {shown.changed.map((line) => (
                  <li key={`${line.customer_id}-${line.old_rate}`}>
                    {line.code} · {line.name} — was {String(line.old_rate ?? "—")}
                  </li>
                ))}
              </ul>
            ) : null}
            {shown.skipped.length ? (
              <ul className="text-xs text-muted-foreground" data-testid="rate-change-skipped">
                {shown.skipped.map((line) => (
                  <li key={`${line.customer_id}-${line.reason}`}>
                    {line.code} {line.name ? `· ${line.name}` : ""} — skipped: {line.reason}
                  </li>
                ))}
              </ul>
            ) : null}
            {shown.preview ? (
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={busy || shown.changed.length === 0}
                  onClick={() => void run(true)}
                >
                  Apply to {shown.changed.length} plan(s)
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
