"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type MonthCell,
  type MonthRow,
  type MonthSheet,
  type Product,
  type Route,
  amendDelivery,
  describeError,
  getMonthSheet,
  listProducts,
  listRoutes,
  monthSheetCsvUrl,
  recordDelivery,
} from "@/lib/api";
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
import { formatAmount } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";

/**
 * The month sheet — the shop's register, computed (WO-84).
 *
 * The client's `Dailymilk Delivery 025.xlsx`: a frozen first column
 * (customer, price), thirty-one narrow day columns, then the totals block
 * in THEIR order — Total milk · Other items · Past due · Total · Received ·
 * Method · Date. This page is that sheet, read from one platform call.
 *
 * Three rules the sheet keeps:
 *
 *  * A blank cell is blank. Not "0", not "—". A scheduled or skipped day is
 *    not a delivery (DEMO-016), and the platform sends null for it.
 *  * Nothing on this page multiplies. Every figure is the platform's.
 *  * Editing goes through `record` and `amend`, the same two calls the
 *    Deliveries page makes, behind the same permission — so the audit trail,
 *    the pricing and the invoice lock are the ones already tested. A cell
 *    already on an issued invoice is read-only and says why. Nothing here
 *    writes in bulk.
 *
 * The day columns scroll horizontally inside their own container; the page
 * does not. Tabular numerals, so digits line up down a column.
 */

function monthOf(iso: string): { year: number; month: number } {
  const [y, m] = iso.split("-").map(Number);
  return { year: y, month: m };
}

function monthLabel(year: number, month: number): string {
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** `1.000` reads as `1`, `1.500` as `1.5` — the way their sheet writes it. */
function plain(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return String(n);
}

function moneyOrBlank(value: string | number): string {
  return Number(value) === 0 ? "" : formatAmount(value);
}

export default function MonthSheetPage() {
  const today = useBusinessToday();
  // DEMO-019: the default month is the ORGANISATION's current month — the
  // platform's business date, never the browser's clock. Derived, not
  // synchronised: the chosen month overrides it once the person moves.
  const [chosen, setChosen] = useState<{ year: number; month: number } | null>(null);
  const period = chosen ?? (today ? monthOf(today) : null);
  const [product, setProduct] = useState("");
  const [routeId, setRouteId] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [sheet, setSheet] = useState<MonthSheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<{
    row: MonthRow;
    day: number;
    cell: MonthCell | null;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      listProducts().then((p) => setProducts(p.items ?? [])).catch(() => setProducts([]));
      listRoutes().then(setRoutes).catch(() => setRoutes([]));
    }, 0);
    return () => clearTimeout(t);
  }, []);

  const load = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    setError(null);
    try {
      setSheet(
        await getMonthSheet({
          year: period.year,
          month: period.month,
          product: product || undefined,
          route_id: routeId || undefined,
        }),
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [period, product, routeId]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  const days = useMemo(() => (sheet ? sheet.day_totals.length : 0), [sheet]);
  // Marked from the PLATFORM's business date, which the sheet carries: the
  // browser's clock is the wrong calendar for a dairy in another zone.
  const todayIndex = useMemo(() => {
    if (!sheet) return -1;
    if (sheet.today < sheet.date_from || sheet.today > sheet.date_to) return -1;
    return Number(sheet.today.slice(8, 10)) - 1;
  }, [sheet]);

  function shift(delta: number) {
    if (!period) return;
    const d = new Date(Date.UTC(period.year, period.month - 1 + delta, 1));
    setChosen({ year: d.getUTCFullYear(), month: d.getUTCMonth() + 1 });
  }

  const csvHref = period
    ? monthSheetCsvUrl({
        year: period.year,
        month: period.month,
        product: product || undefined,
        route_id: routeId || undefined,
      })
    : "#";

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[{ label: "Deliveries", href: "/deliveries" }, { label: "Month sheet" }]}
        title={period ? monthLabel(period.year, period.month) : "Month sheet"}
        description="One row per household and product, a cell per day, the month's totals in the order of the sheet you already keep. A blank cell is a day nothing was delivered."
        actions={
          <span className="inline-flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => shift(-1)}>
              Previous month
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => shift(1)}>
              Next month
            </Button>
            <a
              href={csvHref}
              data-testid="month-sheet-csv"
              className="inline-flex h-8 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-accent"
            >
              Download CSV
            </a>
          </span>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="month-product">Product</Label>
          <Select
            id="month-product"
            value={product}
            onChange={(e) => setProduct(e.target.value)}
          >
            <option value="">All products (one row per product)</option>
            {products.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="month-route">Route</Label>
          <Select id="month-route" value={routeId} onChange={(e) => setRouteId(e.target.value)}>
            <option value="">All households</option>
            {routes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.code} · {r.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {notice ? (
        <p role="status" className="rounded-md bg-muted px-4 py-3 text-sm">
          {notice}
        </p>
      ) : null}

      {editing && sheet ? (
        <CellEditor
          sheet={sheet}
          row={editing.row}
          day={editing.day}
          cell={editing.cell}
          onCancel={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            setNotice(message);
            void load();
          }}
        />
      ) : null}

      {error ? (
        <ErrorState message={error} />
      ) : loading || !sheet ? (
        <LoadingState label="Computing the month…" />
      ) : sheet.rows.length === 0 ? (
        <EmptyState
          title="No standing orders this month"
          description="A household appears once it has an active plan, or a delivery in this month."
        />
      ) : (
        <div
          className="overflow-x-auto rounded-md border border-border"
          data-testid="month-sheet"
        >
          <table className="min-w-max text-sm tabular-nums" aria-label="Month sheet">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="sticky left-0 z-10 bg-muted px-3 py-2 text-left">
                  Customer
                </th>
                <th scope="col" className="px-2 py-2 text-right">
                  Price
                </th>
                {Array.from({ length: days }, (_, i) => (
                  <th
                    key={i}
                    scope="col"
                    data-today={i === todayIndex ? "true" : undefined}
                    className={`w-10 px-1 py-2 text-center ${
                      i === todayIndex ? "bg-primary/10 font-semibold text-foreground" : ""
                    }`}
                  >
                    {i + 1}
                  </th>
                ))}
                <th scope="col" className="px-2 py-2 text-right">Total milk</th>
                <th scope="col" className="px-2 py-2 text-right">Other items</th>
                <th scope="col" className="px-2 py-2 text-right">Past due</th>
                <th scope="col" className="px-2 py-2 text-right">Total</th>
                <th scope="col" className="px-2 py-2 text-right">Received</th>
                <th scope="col" className="px-2 py-2 text-left">Method</th>
                <th scope="col" className="px-2 py-2 text-left">Date</th>
              </tr>
            </thead>
            <tbody>
              {sheet.rows.map((row) => (
                <tr
                  key={`${row.customer_id}-${row.product}`}
                  className="border-t border-border"
                  data-testid={`month-row-${row.code}-${row.product}`}
                >
                  <th
                    scope="row"
                    className="sticky left-0 z-10 bg-background px-3 py-1 text-left font-medium"
                  >
                    <span className="block">{row.name}</span>
                    <span className="block text-xs font-normal text-muted-foreground">
                      {row.code} · {row.product}
                    </span>
                  </th>
                  <td className="px-2 py-1 text-right">
                    {row.unit_price === null ? "" : plain(row.unit_price)}
                  </td>
                  {row.days.map((cell, i) => {
                    const text = cell === null ? "" : plain(cell.quantity);
                    const kind =
                      cell === null
                        ? ""
                        : cell.billed
                          ? "billed"
                          : cell.quantity === null
                            ? cell.status ?? ""
                            : "delivered";
                    const overridden = cell?.price_source === "override";
                    return (
                      <td
                        key={i}
                        data-day={i + 1}
                        data-kind={kind || undefined}
                        data-override={overridden ? "true" : undefined}
                        className={`px-0 py-0 text-center ${
                          i === todayIndex ? "bg-primary/5" : ""
                        }`}
                      >
                        <button
                          type="button"
                          className="h-8 w-10 hover:bg-muted"
                          aria-label={`${row.name} ${row.product} day ${i + 1}${
                            text ? `: ${text}` : ""
                          }${overridden ? " (rate agreed for this day)" : ""}`}
                          onClick={() => setEditing({ row, day: i + 1, cell })}
                        >
                          {text}
                          {overridden ? (
                            <span aria-hidden className="ms-0.5 text-primary">
                              •
                            </span>
                          ) : null}
                        </button>
                      </td>
                    );
                  })}
                  <td className="px-2 py-1 text-right">{plain(row.total_quantity)}</td>
                  <td className="px-2 py-1 text-right">{moneyOrBlank(row.items_amount)}</td>
                  <td className="px-2 py-1 text-right">{moneyOrBlank(row.previous_balance)}</td>
                  <td className="px-2 py-1 text-right font-medium">
                    {formatAmount(row.total_due)}
                  </td>
                  <td className="px-2 py-1 text-right">{moneyOrBlank(row.received)}</td>
                  <td className="px-2 py-1">{row.method ?? ""}</td>
                  <td className="px-2 py-1">{row.received_on ?? ""}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-border bg-muted/30 font-medium">
              <tr data-testid="month-totals">
                <th scope="row" className="sticky left-0 z-10 bg-muted px-3 py-2 text-left">
                  Total ({sheet.quantity_unit})
                </th>
                <td />
                {sheet.day_totals.map((q, i) => (
                  <td key={i} className="px-1 py-2 text-center">
                    {Number(q) === 0 ? "" : plain(q)}
                  </td>
                ))}
                <td className="px-2 py-2 text-right">{plain(sheet.totals.quantity)}</td>
                <td className="px-2 py-2 text-right">{formatAmount(sheet.totals.items_amount)}</td>
                <td className="px-2 py-2 text-right">
                  {formatAmount(sheet.totals.previous_balance)}
                </td>
                <td className="px-2 py-2 text-right">{formatAmount(sheet.totals.total_due)}</td>
                <td className="px-2 py-2 text-right">{formatAmount(sheet.totals.received)}</td>
                <td />
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </PageContainer>
  );
}

/**
 * One cell, opened. Three cases, each through the calls that already exist:
 *
 *  * on an issued invoice → read-only, and it says why (BR-0010);
 *  * a delivery exists (delivered, skipped, scheduled) → `amend`;
 *  * nothing exists → `record`, with the row's product.
 */
function CellEditor({
  sheet,
  row,
  day,
  cell,
  onCancel,
  onSaved,
}: {
  sheet: MonthSheet;
  row: MonthRow;
  day: number;
  cell: MonthCell | null;
  onCancel: () => void;
  onSaved: (message: string) => void;
}) {
  const date = `${sheet.date_from.slice(0, 8)}${String(day).padStart(2, "0")}`;
  const [quantity, setQuantity] = useState(
    cell?.quantity !== null && cell?.quantity !== undefined
      ? plain(cell.quantity)
      : "",
  );
  const [status, setStatus] = useState(
    cell?.status && cell.status !== "scheduled" ? cell.status : "delivered",
  );
  // WO-89: a rate for THIS day. Blank means the plan's rate; the platform
  // refuses a typed one from anybody without `sales.delivery.price`, and
  // the refusal is shown rather than the price being quietly dropped.
  const [price, setPrice] = useState(
    cell?.price_source === "override" && cell.unit_price !== null && cell.unit_price !== undefined
      ? plain(cell.unit_price)
      : "",
  );
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const billed = cell?.billed ?? false;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFailure(null);
    try {
      const priced = price.trim();
      if (cell?.delivery_id) {
        await amendDelivery(cell.delivery_id, {
          quantity: status === "delivered" ? quantity.trim() : "0",
          status,
          ...(priced ? { unit_price: priced } : {}),
          ...(!priced && cell.price_source === "override" ? { clear_price: true } : {}),
        });
        onSaved(`${row.name}, day ${day}: corrected. The platform recomputed the amount from the agreed rate.`);
      } else {
        await recordDelivery({
          customer_id: row.customer_id,
          delivery_date: date,
          product: row.product,
          status,
          ...(status === "delivered" && quantity.trim() ? { quantity: quantity.trim() } : {}),
          ...(priced ? { unit_price: priced } : {}),
        });
        onSaved(`${row.name}, day ${day}: recorded.`);
      }
    } catch (err) {
      setFailure(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card data-testid="month-cell-editor">
      <CardHeader>
        <CardTitle className="text-base">
          {row.name} · {row.product} · {date}
        </CardTitle>
        <CardDescription>
          {billed
            ? "This delivery is on an invoice that has been issued. An issued invoice is immutable; correct it with an adjustment on the next one, not by editing this cell."
            : cell?.delivery_id
              ? `Recorded as ${cell.status}. Set the quantity, mark it skipped, or put it right — the amount is recomputed by the platform from the agreed rate${
                  row.unit_price !== null ? ` (${plain(row.unit_price)} ${sheet.currency} per ${row.quantity_unit})` : ""
                }.`
              : "Nothing is recorded for this day. Record what was delivered, or mark it skipped; the rate is the household's agreed rate and is never typed here."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {billed ? (
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              Close
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="cell-status">Status</Label>
              <Select id="cell-status" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="delivered">delivered</option>
                <option value="skipped">skipped</option>
              </Select>
            </div>
            {status === "delivered" ? (
              <div className="flex flex-col gap-1">
                <Label htmlFor="cell-quantity">Quantity ({row.quantity_unit})</Label>
                <Input
                  id="cell-quantity"
                  inputMode="decimal"
                  value={quantity}
                  placeholder="standing order"
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </div>
            ) : null}
            {status === "delivered" ? (
              <div className="flex flex-col gap-1">
                <Label htmlFor="cell-price">
                  Rate for this day ({sheet.currency} per {row.quantity_unit})
                </Label>
                <Input
                  id="cell-price"
                  inputMode="decimal"
                  value={price}
                  placeholder={row.unit_price === null ? "plan's rate" : `plan: ${plain(row.unit_price)}`}
                  onChange={(e) => setPrice(e.target.value)}
                />
              </div>
            ) : null}
            <Button type="submit" size="sm" disabled={saving}>
              {cell?.delivery_id ? "Correct" : "Record"}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            {failure ? (
              <p role="alert" className="basis-full text-sm text-destructive">
                The platform refused: {failure}
              </p>
            ) : null}
          </form>
        )}
      </CardContent>
    </Card>
  );
}
