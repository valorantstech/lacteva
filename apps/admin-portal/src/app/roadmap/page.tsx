"use client";

import Link from "next/link";
import { PageHeader, SectionHeading } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { PageContainer } from "@/components/page-container";

/**
 * The roadmap visibility page (P0-PRODUCT-VISIBILITY-001).
 *
 * Lacteva's shipping surface is deliberately honest: every other page in this
 * portal is a real, API-backed capability, and nothing here pretends a feature
 * exists before it does. What the product lacked was the OTHER half of that
 * honesty — a place that says, plainly, "these are on the roadmap and are NOT
 * available today," so a Coming-Soon capability is never mistaken for a shipped
 * one.
 *
 * This page is INFORMATIONAL and NON-INTERACTIVE by design. It calls no API,
 * shows no data, and offers no control that does anything. Every classification
 * below is copied from the canonical `LACTEVA-MASTER-PRODUCT-ROADMAP.md`
 * (NOW / V1 / V1+ / V2 / ENTERPRISE / FUTURE OPTION) — none is invented here,
 * and none is a commitment or a date. The roadmap's own Coming-Soon policy
 * (§13) allows exactly this: non-interactive labels that never look operational.
 */

type Phase = "V1" | "V2" | "Enterprise" | "Future";

type Item = {
  name: string;
  detail: string;
  phase: Phase;
};

// Available today — real, shipped capabilities, each linking to its real page.
// This is the CONTRAST that makes the roadmap honest: what you can use now,
// beside what is still coming.
const AVAILABLE: { name: string; href: string; detail: string }[] = [
  {
    name: "Collection & quality capture",
    href: "/transactions",
    detail:
      "Weigh milk and record FAT / SNF / CLR at the centre — on the web and the phone, online or offline.",
  },
  {
    name: "Rate cards",
    href: "/rate-cards",
    detail:
      "The dairy's own FAT-banded rate chart, per product and centre, priced automatically once published.",
  },
  {
    name: "Parchi (collection slip)",
    href: "/transactions",
    detail:
      "A numbered receipt for every completed collection, ready to print or share as text.",
  },
  {
    name: "Settlement",
    href: "/settlements",
    detail:
      "Farmer payments reconciled line-by-line to the collections behind them, on the dairy's own cycle.",
  },
  {
    name: "Customers & delivery",
    href: "/customers",
    detail:
      "Outlets, standing orders, routes and delivery runs — the distribution side, not just procurement.",
  },
  {
    name: "Billing & receivables",
    href: "/billing",
    detail:
      "Invoices drafted from real deliveries; a person reviews and issues them; receivables tracked.",
  },
  {
    name: "Reports & dashboard",
    href: "/reports",
    detail:
      "Operational reports and a live owner dashboard across every collection centre.",
  },
  {
    name: "Subscription & trial",
    href: "/admin/subscription",
    detail:
      "Per-centre plan and 30-day trial. The platform shows what the dairy is entitled to; taking payment is not yet wired (see below).",
  },
];

// Roadmap — classified verbatim from LACTEVA-MASTER-PRODUCT-ROADMAP.md.
// Nothing below is operational.
const COMING_SOON: Item[] = [
  {
    name: "Messaging (WhatsApp / SMS)",
    detail:
      "Sending the parchi and reminders by WhatsApp or SMS. The adapter exists; a messaging provider (DLT/BSP paperwork) is not yet contracted, so nothing is sent today. Email templating is present.",
    phase: "V1",
  },
  {
    name: "Automated scale & analyzer capture",
    detail:
      "Reading weight and quality directly from a centre's scale/analyzer instead of typing them. Discovery-gated on a device visit; capture is manual-first today, and mock readings are refused in production.",
    phase: "V1",
  },
  {
    name: "QR / barcode supplier scanning",
    detail:
      "Scanning a farmer's code at the wizard instead of typing it. The supplier code is entered by hand today.",
    phase: "V1",
  },
  {
    name: "Receipt & invoice PDF download",
    detail:
      "A downloadable PDF document. Receipts render on screen and copy to clipboard today; there is no PDF engine yet.",
    phase: "V1",
  },
  {
    name: "GST / FSSAI fields on documents",
    detail:
      "Statutory identifiers printed on invoices and slips. Not built; the dairy remains responsible for its own regulatory obligations.",
    phase: "V1",
  },
  {
    name: "Quality & settlement anomaly detection",
    detail:
      "Beyond today's non-blocking FAT/SNF deviation flag (which is statistics, not ML) — broader anomaly detection across quality, settlement and operator patterns.",
    phase: "V1",
  },
  {
    name: "Collection & demand forecasting",
    detail:
      "Forecasting supply and demand from history. Needs a real data history first; not built.",
    phase: "V2",
  },
  {
    name: "Chilling centre / BMC",
    detail:
      "Modelling a bulk-milk cooler as an asset at a location, and chilling centres as a location type. Not built.",
    phase: "V2",
  },
  {
    name: "Procurement transport",
    detail:
      "The centre → chilling → plant movement of milk, kept distinct from customer delivery. Not built.",
    phase: "V2",
  },
  {
    name: "Plant / processing operations",
    detail: "Processing beyond collection and distribution. Not built.",
    phase: "V2",
  },
];

const ENTERPRISE: Item[] = [
  {
    name: "SAP / ERP integration",
    detail:
      "Connecting Lacteva to an enterprise ERP. No vendor, module names or protocol are chosen or assumed. Reserved for a signed enterprise engagement.",
    phase: "Enterprise",
  },
  {
    name: "Enterprise SSO",
    detail:
      "Single sign-on against a corporate identity provider. No provider chosen; not built.",
    phase: "Enterprise",
  },
  {
    name: "Global identity (one person, many organizations)",
    detail:
      "One login spanning multiple dairies, without ever widening tenant isolation. Reserved for enterprise scale.",
    phase: "Enterprise",
  },
  {
    name: "Organization-to-organization / federation",
    detail:
      "Parent groups and consented cross-organization visibility, always through projections and never a relaxed database boundary. Not built.",
    phase: "Enterprise",
  },
];

const FUTURE: Item[] = [
  {
    name: "Farmer self-service app",
    detail:
      "A milk producer's own app. Today a farmer is served by an operator at the centre and receives a parchi — there is no farmer login.",
    phase: "Future",
  },
  {
    name: "Web customer / outlet portal",
    detail:
      "A browser portal for outlets. (A household customer already has a screen in the mobile app; a separate web outlet portal is a future option.)",
    phase: "Future",
  },
  {
    name: "Advanced AI",
    detail:
      "Machine-learning capabilities beyond the current statistical deviation flag. No AI vendor and no ML model exist in the product today.",
    phase: "Future",
  },
];

function PhaseBadge({ phase }: { phase: Phase }) {
  // Two treatments only, matching the roadmap's allowed vocabulary: an
  // "Enterprise" chip for enterprise-stage items, "Coming soon" for everything
  // else. The specific phase (V1 / V2 / Future) rides along as the label so the
  // reader sees roughly how far out it is without it ever reading as a promise.
  if (phase === "Enterprise") {
    return <Badge variant="outline">Enterprise</Badge>;
  }
  const label =
    phase === "V2"
      ? "Coming soon · Later"
      : phase === "Future"
        ? "Coming soon · Future option"
        : "Coming soon";
  return <Badge variant="secondary">{label}</Badge>;
}

function RoadmapItem({ item }: { item: Item }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium">{item.name}</p>
        <PhaseBadge phase={item.phase} />
      </div>
      <p className="text-sm text-muted-foreground">{item.detail}</p>
    </div>
  );
}

export default function RoadmapPage() {
  return (
    <PageContainer width="default">
      <PageHeader
        title="What you can use today, and what's on the roadmap"
        description="Lacteva shows only real capabilities in the product. This page keeps the two categories separate: everything you can use today has its own page in this portal; everything below is on the roadmap and is NOT available yet. Nothing here is a commitment or a date."
      />

      <section className="flex flex-col gap-3">
        <SectionHeading
          title="Available today"
          detail="Real, shipped capabilities. Each opens its own page."
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {AVAILABLE.map((c) => (
            <Link
              key={c.name}
              href={c.href}
              className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-muted/40"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-medium">{c.name}</p>
                <Badge variant="default">Available</Badge>
              </div>
              <p className="text-sm text-muted-foreground">{c.detail}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionHeading
          title="Coming soon"
          detail="On the roadmap and not available today. No fake screens, data, or readings sit behind these."
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {COMING_SOON.map((item) => (
            <RoadmapItem key={item.name} item={item} />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionHeading
          title="Enterprise"
          detail="Reserved for enterprise-stage engagements. Not generally available, and never presented as operational."
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {ENTERPRISE.map((item) => (
            <RoadmapItem key={item.name} item={item} />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionHeading
          title="Future options"
          detail="Directional only — capabilities the platform is built to grow into when there is a real need."
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {FUTURE.map((item) => (
            <RoadmapItem key={item.name} item={item} />
          ))}
        </div>
      </section>

      <p className="border-t border-border pt-5 text-xs text-muted-foreground">
        Classification source: LACTEVA-MASTER-PRODUCT-ROADMAP.md. Statuses are
        NOW / V1 / V2 / Enterprise / Future option; this page never turns a
        roadmap item into a working control.
      </p>
    </PageContainer>
  );
}
