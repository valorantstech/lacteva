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
 * A quantity with its unit. Same rule: the value arrives formatted by the
 * domain (`40.000`), and the trailing zeros are significant — they say the
 * scale reads to three decimal places.
 */
export function Quantity({
  value,
  unit = "kg",
  className,
}: {
  value: string | number | null | undefined;
  unit?: string | null;
  className?: string;
}) {
  const formatted = formatAmount(value);
  return (
    <span className={cn("tabular-nums whitespace-nowrap", className)}>
      {formatted}
      {unit && formatted !== "—" ? (
        <span className="ms-1 text-xs text-muted-foreground">{unit}</span>
      ) : null}
    </span>
  );
}
