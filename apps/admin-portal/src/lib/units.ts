/**
 * The intake unit — the dairy's, never the code's (D-21 / WO-70).
 *
 * The platform stores a unit WORD on every record (`litre`, `kg`) and every
 * aggregate carries the unit of the rows it summed (`quantity_unit`, which
 * says `mixed` when a window straddles an owner's change of unit). This is
 * the one place the word becomes a symbol. Nothing in the portal may write
 * `kg` next to a number it did not read a unit for — `units.test.ts` greps
 * for the literal.
 */
const LABELS: Record<string, string> = {
  litre: "L",
  litres: "L",
  liter: "L",
  l: "L",
  kg: "kg",
  kilogram: "kg",
  kilograms: "kg",
};

/** `litre` → `L`, `kg` → `kg`; anything else — `mixed`, `L` itself — as sent. */
export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return "";
  return LABELS[unit.toLowerCase()] ?? unit;
}

/** The units an organisation may measure in, as the platform names them. */
export const UNITS = ["litre", "kg"] as const;
