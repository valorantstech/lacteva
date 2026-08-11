/**
 * One vocabulary for status across the whole portal (DEMO-001).
 *
 * The platform has a lot of lifecycles — supplier, transaction, settlement,
 * payment, receipt, rate card, device — and they mostly agree about what a
 * word means: `draft` is not yet real, `active`/`completed`/`finalized` is
 * good and done, `failed`/`rejected` needs someone, `archived`/`cancelled` is
 * over. Mapping them centrally means "completed" looks the same on the
 * payments screen as on the collections screen, which is how someone learns
 * the product in one sitting rather than six.
 *
 * ACCESSIBILITY: the label is always the status word itself, so meaning never
 * depends on colour. A red badge and a grey badge both say what they are.
 */

import { Badge } from "@/components/ui/badge";

type Variant = "default" | "secondary" | "destructive" | "outline";

const GOOD = new Set([
  "active", "completed", "finalized", "published", "paid", "succeeded",
  "generated", "delivered", "ready", "accepted", "healthy", "ok",
]);
const PENDING = new Set([
  "draft", "pending", "processing", "calculated", "submitted", "approved",
  "queued", "in_progress", "quality_pending", "pricing_pending", "open",
  "new", "supplier_identified", "milk_received", "priced", "sent",
]);
const BAD = new Set([
  "failed", "rejected", "error", "dead", "unhealthy", "expired", "overdue",
]);
const OVER = new Set([
  "archived", "cancelled", "canceled", "closed", "suspended", "inactive",
  "offboarded", "superseded", "retired",
]);

export function statusVariant(status: string | null | undefined): Variant {
  const key = String(status ?? "").toLowerCase();
  if (GOOD.has(key)) return "default";
  if (BAD.has(key)) return "destructive";
  if (OVER.has(key)) return "outline";
  if (PENDING.has(key)) return "secondary";
  return "secondary";
}

/** Human wording for a machine token: `QUALITY_PENDING` → `quality pending`. */
export function statusLabel(status: string | null | undefined): string {
  const raw = String(status ?? "").trim();
  if (!raw) return "unknown";
  return raw.toLowerCase().replace(/[_-]+/g, " ");
}

export function StatusBadge({
  status,
  className,
}: {
  status: string | null | undefined;
  className?: string;
}) {
  return (
    <Badge variant={statusVariant(status)} className={className}>
      {statusLabel(status)}
    </Badge>
  );
}
