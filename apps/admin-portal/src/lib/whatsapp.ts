/**
 * "Send on WhatsApp", with no provider (WO-83 §3).
 *
 * A `wa.me` link opens WhatsApp with the recipient and a prefilled message;
 * the OWNER presses Send. Nothing is sent by Lacteva — which is the point,
 * and what makes it possible today. The number must be international digits
 * with no `+`, spaces or punctuation: `+91 98450 12345` → `919845012345`.
 */
export function waMeNumber(phone: string | null | undefined): string | null {
  const digits = (phone ?? "").replace(/[^\d]/g, "");
  // A local number without a country code cannot be dialled from wa.me;
  // the platform stores E.164 (WO-81 seeds and imports carry the +), so a
  // number shorter than a country code plus a subscriber number is refused.
  if (digits.length < 8) return null;
  return digits;
}

export function waMeLink(phone: string | null | undefined, text: string): string | null {
  const number = waMeNumber(phone);
  if (!number) return null;
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}

/** The message a household reads before opening the bill (WO-83 §3). */
export function billSummary(input: {
  organization: string;
  invoice_number: string;
  period_from: string;
  period_to: string;
  currency: string;
  delivered_quantity?: string | number | null;
  quantity_unit?: string | null;
  items_count?: number | null;
  total: string | number;
  previous_balance: string | number;
  amount_due: string | number;
  pay_to?: string | null;
}): string {
  const lines = [
    `${input.organization} — bill ${input.invoice_number} for ${input.period_from} to ${input.period_to}.`,
  ];
  if (input.delivered_quantity !== null && input.delivered_quantity !== undefined) {
    lines.push(`Milk delivered: ${input.delivered_quantity} ${input.quantity_unit ?? ""}`.trim());
  }
  if (input.items_count) lines.push(`Other items: ${input.items_count}`);
  lines.push(`Total: ${input.total} ${input.currency}`);
  const previous = Number(input.previous_balance);
  if (previous < 0) lines.push(`Advance: ${Math.abs(previous).toFixed(2)} ${input.currency}`);
  else if (previous > 0) lines.push(`Previous balance: ${input.previous_balance} ${input.currency}`);
  lines.push(`Amount due: ${input.amount_due} ${input.currency}`);
  if (input.pay_to) lines.push(`Pay to: ${input.pay_to}`);
  lines.push("Your detailed bill is available from the shop.");
  return lines.join("\n");
}
