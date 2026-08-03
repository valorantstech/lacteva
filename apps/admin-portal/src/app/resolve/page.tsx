"use client";

import { useEffect, useState } from "react";
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
  ApiError,
  CalculationResult,
  Center,
  QualityDimension,
  ResolutionOutcome,
  calculatePricing,
  listCenters,
  listQualityDimensions,
  resolvePricing,
} from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  dimension: "Quality dimension",
  rate_card: "Rate card",
  matrix: "Pricing matrix",
  band: "Price band",
};

export default function ResolutionPlaygroundPage() {
  const [centers, setCenters] = useState<Center[]>([]);
  const [dimensions, setDimensions] = useState<QualityDimension[]>([]);
  const [centerId, setCenterId] = useState("");
  const [productCode, setProductCode] = useState("");
  const [date, setDate] = useState("");
  const [dimensionCode, setDimensionCode] = useState("");
  const [value, setValue] = useState("");
  const [outcome, setOutcome] = useState<ResolutionOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [quantity, setQuantity] = useState("");
  const [policy, setPolicy] = useState("");
  const [calc, setCalc] = useState<CalculationResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calcBusy, setCalcBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      listCenters({ limit: 100, offset: 0 })
        .then((p) => setCenters(p.items))
        .catch(() => setCenters([]));
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
    setOutcome(null);
    setCalc(null);
    setCalcError(null);
    try {
      setOutcome(
        await resolvePricing({
          center_id: centerId,
          product_code: productCode,
          transaction_date: date,
          dimension_code: dimensionCode,
          value: Number(value),
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Resolution request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Resolution playground</h1>
        <p className="text-sm text-muted-foreground">
          &ldquo;What pricing matrix would this transaction use?&rdquo; — selection only, no
          amounts are calculated
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Simulated transaction</CardTitle>
          <CardDescription>
            The engine selects exactly one published rate card, one matrix, and one price band —
            or tells you precisely why it cannot.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid max-w-2xl grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-center">Collection center</Label>
              <select
                id="r-center"
                required
                className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                value={centerId}
                onChange={(e) => setCenterId(e.target.value)}
              >
                <option value="">Select…</option>
                {centers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-product">Product code</Label>
              <Input
                id="r-product"
                required
                placeholder="e.g. RAW-COW-MILK"
                value={productCode}
                onChange={(e) => setProductCode(e.target.value.toUpperCase())}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-date">Transaction date</Label>
              <Input
                id="r-date"
                type="date"
                required
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-dimension">Quality dimension</Label>
              <select
                id="r-dimension"
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
                      {d.unit ? ` (${d.unit})` : ""}
                    </option>
                  ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="r-value">Reading</Label>
              <Input
                id="r-value"
                required
                type="number"
                step="any"
                placeholder="e.g. 4.2"
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </div>
            {error && <p className="col-span-2 text-sm text-destructive">{error}</p>}
            <div className="col-span-2">
              <Button type="submit" disabled={busy}>
                {busy ? "Resolving…" : "Resolve"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {outcome?.ok && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              Matched <Badge>1 of 1</Badge>
            </CardTitle>
            <CardDescription>
              Resolved at {String(outcome.result.metadata.resolved_at ?? "")}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div>
              <span className="font-medium">Rate card:</span>{" "}
              <code className="rounded bg-muted px-1">
                {outcome.result.rate_card_code} v{outcome.result.rate_card_version}
              </code>{" "}
              ({String(outcome.result.metadata.effective_from)} →{" "}
              {String(outcome.result.metadata.effective_until ?? "open")})
            </div>
            <div>
              <span className="font-medium">Matrix:</span> {outcome.result.matrix_name} ·{" "}
              {String(outcome.result.metadata.product_code)} ·{" "}
              {String(outcome.result.metadata.dimension_code)}
            </div>
            <div>
              <span className="font-medium">Band:</span>{" "}
              <code className="rounded bg-muted px-1">
                [{outcome.result.matching_range.from_value} –{" "}
                {outcome.result.matching_range.to_value})
              </code>{" "}
              for reading {outcome.result.reading.value}
              {outcome.result.reading.unit}
            </div>
            <div className="text-lg">
              <span className="font-medium">Unit price:</span>{" "}
              {String(outcome.result.unit_price.amount)} {outcome.result.unit_price.currency}
            </div>
            <div className="flex flex-wrap items-end gap-2 border-t border-border pt-3">
              <div className="flex flex-col gap-1">
                <Label htmlFor="c-quantity">Quantity (kg)</Label>
                <Input
                  id="c-quantity"
                  type="number"
                  step="any"
                  min="0"
                  className="h-8 w-32"
                  placeholder="e.g. 125.5"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="c-policy">Rounding</Label>
                <select
                  id="c-policy"
                  className="h-8 rounded-lg border border-border bg-background px-2 text-sm"
                  value={policy}
                  onChange={(e) => setPolicy(e.target.value)}
                >
                  <option value="">Tenant default</option>
                  <option value="HALF_UP">HALF_UP</option>
                  <option value="HALF_EVEN">HALF_EVEN</option>
                  <option value="DOWN">DOWN</option>
                </select>
              </div>
              <Button
                size="sm"
                disabled={calcBusy || !quantity}
                onClick={async () => {
                  setCalcBusy(true);
                  setCalcError(null);
                  try {
                    setCalc(
                      await calculatePricing({
                        row_id: outcome.result.row_id,
                        quantity: Number(quantity),
                        transaction_date: date,
                        ...(policy ? { rounding_policy: policy } : {}),
                      }),
                    );
                  } catch (err) {
                    setCalcError(
                      err instanceof ApiError ? err.detail : "Calculation failed",
                    );
                  } finally {
                    setCalcBusy(false);
                  }
                }}
              >
                {calcBusy ? "Calculating…" : "Calculate"}
              </Button>
              {calcError && <p className="text-sm text-destructive">{calcError}</p>}
            </div>
          </CardContent>
        </Card>
      )}

      {calc && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              Gross amount: {String(calc.gross_amount.amount)} {calc.currency}
              <Badge variant="outline">{calc.rounding_policy}</Badge>
            </CardTitle>
            <CardDescription>
              {String(calc.unit_price.amount)} {calc.currency} × {calc.quantity.value}{" "}
              {calc.quantity.unit} · calculator v{calc.calculator_version} ·{" "}
              {calc.resolution.rate_card_code} v{calc.resolution.rate_card_version} /{" "}
              {calc.resolution.matrix_name}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <p className="mb-2 font-medium">Calculation trace</p>
            <ol className="flex flex-col gap-1">
              {calc.trace.map((step) => (
                <li key={step.sequence} className="flex gap-2">
                  <Badge variant="secondary">{step.operation}</Badge>
                  <span>
                    {step.detail}
                    {step.values.raw_amount && step.operation === "multiply" && (
                      <> — raw: <code className="rounded bg-muted px-1">{step.values.raw_amount}</code></>
                    )}
                    {step.operation === "round" && (
                      <>
                        {" "}
                        — <code className="rounded bg-muted px-1">{step.values.raw_amount}</code> →{" "}
                        <code className="rounded bg-muted px-1">{step.values.rounded_amount}</code>
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-muted-foreground">
              No bonuses, penalties, or taxes — those arrive with PRC-005+.
            </p>
          </CardContent>
        </Card>
      )}

      {outcome && !outcome.ok && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3">
              No resolution
              <Badge variant={outcome.failure.status === 409 ? "destructive" : "secondary"}>
                {outcome.failure.status === 409 ? "integrity problem" : "no match"}
              </Badge>
              {outcome.failure.stage && (
                <Badge variant="outline">
                  failed at: {STAGE_LABELS[outcome.failure.stage] ?? outcome.failure.stage}
                </Badge>
              )}
            </CardTitle>
            <CardDescription>{outcome.failure.title}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {outcome.failure.reason && <p>{outcome.failure.reason}</p>}
            {outcome.failure.candidates && (
              <p className="text-destructive">
                {outcome.failure.candidates.length} candidates matched where exactly one is
                required — pricing data needs administrator attention.
              </p>
            )}
            {outcome.failure.inputs && (
              <p className="text-muted-foreground">
                Inputs: {JSON.stringify(outcome.failure.inputs)}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </main>
  );
}
