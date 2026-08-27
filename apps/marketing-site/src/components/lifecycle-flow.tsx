import {
  Banknote,
  BarChart3,
  ChevronDown,
  ChevronRight,
  CornerDownLeft,
  FileText,
  Handshake,
  Milk,
  Scale,
  Truck,
  Users,
} from "lucide-react";

/**
 * The signature Lacteva visual: the dairy operating lifecycle as one
 * connected flow. A business workflow, not an architecture diagram —
 * eight stages, one line. Horizontal on desktop, vertical on mobile.
 * Designed for the ink band; every color here assumes the dark surface.
 */
const STAGES = [
  { icon: Handshake, label: "Procurement", detail: "Suppliers, rate cards, quality-based pricing" },
  { icon: Milk, label: "Collection", detail: "Centres, sessions, every litre recorded" },
  { icon: Users, label: "Customers", detail: "Accounts, agreed plans, standing orders" },
  { icon: Truck, label: "Delivery", detail: "Daily rounds, generated automatically" },
  { icon: FileText, label: "Billing", detail: "Invoices and receivables from delivery records" },
  { icon: Banknote, label: "Payments", detail: "Payments and receipts against every bill" },
  { icon: Scale, label: "Settlements", detail: "Supplier payables, exact to the decimal" },
  { icon: BarChart3, label: "Reports", detail: "Operational and financial visibility" },
] as const;

export function LifecycleFlow() {
  return (
    <ol className="flex flex-col gap-1 lg:grid lg:grid-cols-4 lg:gap-y-8">
      {STAGES.map((stage, i) => (
        <li key={stage.label} className="flex flex-col lg:flex-row lg:items-stretch">
          <div className="lacteva-lift flex items-start gap-4 rounded-xl border border-ink-foreground/15 bg-ink-foreground/5 p-4 lg:min-w-0 lg:flex-1 lg:flex-col lg:gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <stage.icon className="size-4.5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink-foreground">
                {stage.label}
              </span>
              <span className="block pt-0.5 text-xs leading-relaxed text-ink-muted">
                {stage.detail}
              </span>
            </span>
          </div>
          {i < STAGES.length - 1 ? (
            <span aria-hidden className="flex justify-center py-0.5 lg:hidden">
              <ChevronDown className="size-4 text-ink-muted" />
            </span>
          ) : null}
          {/* Desktop connector. At the row wrap (stage 4 → 5) the arrow
              turns down-and-left, so the flow reads as one continuous
              line instead of breaking at the row edge (PRE-LAUNCH-001). */}
          {i < STAGES.length - 1 ? (
            <span aria-hidden className="hidden items-center px-1 lg:flex">
              {i === 3 ? (
                <CornerDownLeft className="size-4 shrink-0 text-ink-muted" />
              ) : (
                <ChevronRight className="size-4 shrink-0 text-ink-muted" />
              )}
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
