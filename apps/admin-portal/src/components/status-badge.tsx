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
import { useLocale } from "@/lib/i18n";
import { KEYS } from "@/lib/messages";

type Variant = "default" | "secondary" | "destructive" | "outline";

const GOOD = new Set([
  "active",
  "completed",
  "finalized",
  "published",
  "paid",
  "succeeded",
  "generated",
  "delivered",
  "ready",
  "accepted",
  "healthy",
  "ok",
]);
const PENDING = new Set([
  "draft",
  "pending",
  "processing",
  "calculated",
  "submitted",
  "approved",
  "queued",
  "in_progress",
  "quality_pending",
  "pricing_pending",
  "open",
  "new",
  "supplier_identified",
  "milk_received",
  "priced",
  "sent",
]);
const BAD = new Set([
  "failed",
  "rejected",
  "error",
  "dead",
  "unhealthy",
  "expired",
  "overdue",
]);
const OVER = new Set([
  "archived",
  "cancelled",
  "canceled",
  "closed",
  "suspended",
  "inactive",
  "offboarded",
  "superseded",
  "retired",
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

/**
 * The catalog key for a status, if the catalog has one.
 *
 * DEMO-016. Every badge in this portal printed the machine token in English,
 * on every screen, in every language — including `scheduled`, which this
 * milestone introduced. Translating the WHOLE status vocabulary at once would
 * touch every lifecycle on the platform, so this is the narrow version: a
 * status with a `status.*` key reads in the reader's language, and one
 * without keeps exactly the behaviour it has today.
 *
 * That makes the catalog the thing to extend, not this file — adding a key is
 * how a status becomes translated, and nothing here has to change again.
 */
function keyFor(status: string | null | undefined): string {
  return `status.${String(status ?? "")
    .trim()
    .toLowerCase()}`;
}

export function StatusBadge({
  status,
  className,
}: {
  status: string | null | undefined;
  className?: string;
}) {
  const { t } = useLocale();
  const key = keyFor(status);
  const label = KEYS.includes(key) ? t(key) : statusLabel(status);
  return (
    <Badge variant={statusVariant(status)} className={className}>
      {label}
    </Badge>
  );
}
