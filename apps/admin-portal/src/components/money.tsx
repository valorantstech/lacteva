/**
 * Money, rendered — never computed (DEMO-001).
 *
 * The platform sends every amount as a STRING of exact decimal digits, because
 * it is `Decimal` end to end and `Numeric` in the database. Parsing one into a
 * JavaScript number to add, total or round it would replace exact arithmetic
 * with binary floating point at the last possible moment, which is the one
 * place a money bug is hardest to see and easiest to ship: `0.1 + 0.2` is not
 * `0.3`, and a settlement that disagrees with its own lines by a cent is a
 * settlement no cooperative will sign.
 *
 * So this component formats and never calculates. It splits the string on the
 * decimal point and groups the digits itself — no `Number()`, no `parseFloat`,
 * no `toFixed`. If a total is needed, the backend already has one; ask for it.
 */

import { unitLabel } from "@/lib/units";
import { cn } from "@/lib/utils";

/** Group the integer part in threes without ever leaving string space. */
function groupDigits(digits: string): string {
  const negative = digits.startsWith("-");
  const bare = negative ? digits.slice(1) : digits;
  const grouped = bare.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return negative ? `-${grouped}` : grouped;
}

/**
 * Do two exact-decimal strings denote the same amount?
 *
 * DEMO-002 shipped a reconciliation that reported false mismatches because it
 * compared "353234.00" with "353234.0" as STRINGS. The amounts were identical;
 * the comparison was wrong. Parsing both to `Number` would fix that case and
 * introduce a worse one, so this normalises in string space instead: strip a
 * redundant sign, leading zeros and trailing fractional zeros, then compare.
 *
 * It answers "are these equal", never "what is the difference" — subtraction
 * is the backend's job, and no screen here needs it.
 */
export function sameAmount(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): boolean {
  const normalise = (value: string | number | null | undefined): string | null => {
    if (value === null || value === undefined || value === "") return null;
    const text = String(value).trim();
    if (!/^-?\d+(\.\d+)?$/.test(text)) return null;
    const negative = text.startsWith("-");
    const bare = negative ? text.slice(1) : text;
    let [whole, fraction = ""] = bare.split(".");
    whole = whole.replace(/^0+(?=\d)/, "");
    fraction = fraction.replace(/0+$/, "");
    const zero = whole === "0" && fraction === "";
    return `${zero || !negative ? "" : "-"}${whole}${fraction ? `.${fraction}` : ""}`;
  };
  const left = normalise(a);
  const right = normalise(b);
  return left !== null && right !== null && left === right;
}

export function formatAmount(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text; // not a plain decimal; show as sent
  const [whole, fraction] = text.split(".");
  return fraction ? `${groupDigits(whole)}.${fraction}` : groupDigits(whole);
}

export function Money({
  amount,
  currency,
  className,
  emphasis = false,
}: {
  amount: string | number | null | undefined;
  currency?: string | null;
  className?: string;
  /** Totals and payables — the figure someone is going to act on. */
  emphasis?: boolean;
}) {
  const formatted = formatAmount(amount);
  return (
    <span
      className={cn(
        "tabular-nums whitespace-nowrap",
        emphasis && "font-semibold",
        className,
      )}
    >
      {formatted}
      {currency && formatted !== "—" ? (
        <span className="ms-1 text-xs font-normal text-muted-foreground">{currency}</span>
      ) : null}
    </span>
  );
}

/**
 * A money aggregate, in the currencies it is actually made of (WO-61).
 *
 * The platform answers every money aggregate as a figure PER CURRENCY —
 * `{ "KES": "10147.50" }` — because a tenant holding two currencies has no
 * single total, and adding shillings to rupees is a category error rather
 * than an arithmetic one. This renders what it is given and nothing else:
 * one labelled figure for one currency, a line each for more than one, and a
 * dash for none.
 *
 * It exists because the alternative was a bare number labelled from the
 * ORGANIZATION, which is how the settlements page came to show 10,147.50 INR
 * over four rows of KES on the live host.
 */
export function CurrencyTotals({
  totals,
  className,
  emphasis = false,
}: {
  totals: Record<string, string | number> | null | undefined;
  className?: string;
  emphasis?: boolean;
}) {
  const entries = Object.entries(totals ?? {});
  if (entries.length === 0) return <span className={className}>—</span>;
  if (entries.length === 1) {
    const [currency, amount] = entries[0];
    return (
      <Money
        amount={amount}
        currency={currency}
        className={className}
        emphasis={emphasis}
      />
    );
  }
  // A dairy that genuinely holds two currencies gets two figures. One number
  // here would have to be a sum across currencies, which is not a number.
  return (
    <span className={cn("flex flex-col items-start", className)}>
      {entries.map(([currency, amount]) => (
        <Money key={currency} amount={amount} currency={currency} emphasis={emphasis} />
      ))}
    </span>
  );
}

/**
 * A quantity to ONE decimal, as a dairy says it (WO-68 rider).
 *
 * The domain stores three decimals — `735.000` — because that is what the
 * instrument reads to, and money keeps every decimal it is given. A quantity
 * is different: nobody at a dairy says "seven hundred and thirty-five point
 * zero zero zero litres". WO-64 made the handset say `214.0 L`; the portal
 * kept `735.000 L` on the dashboard and `0.000 L` in the day book. Same
 * change, other client. Anything that is not a plain decimal is shown as
 * sent, as `formatAmount` does.
 */
export function formatQuantity(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = String(value);
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text;
  const rounded = Number(text).toFixed(1);
  const negative = rounded.startsWith("-");
  const [whole, fraction] = (negative ? rounded.slice(1) : rounded).split(".");
  return `${negative ? "-" : ""}${groupDigits(whole)}.${fraction}`;
}

/**
 * A quantity with its unit, to one decimal (see `formatQuantity`).
 */
export function Quantity({
  value,
  unit,
  className,
}: {
  value: string | number | null | undefined;
  /**
   * D-21 / WO-70: the unit READ from the record — a transaction's
   * `weight_unit`, an aggregate's `quantity_unit`. There is no default: this
   * component used to assume `kg`, which put a foreign unit on the first
   * screen of an Indian dairy's first demo. A caller with no unit to hand
   * renders the bare figure, which is at least not a claim.
   */
  unit?: string | null;
  className?: string;
}) {
  const formatted = formatQuantity(value);
  const label = unitLabel(unit);
  return (
    <span className={cn("tabular-nums whitespace-nowrap", className)}>
      {formatted}
      {label && formatted !== "—" ? (
        <span className="ms-1 text-xs text-muted-foreground">{label}</span>
      ) : null}
    </span>
  );
}
