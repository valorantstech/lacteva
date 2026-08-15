import type { Metadata } from "next";
import Link from "next/link";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Product",
  description:
    "How Lacteva works: offline collection, explainable quality-based pricing, one-click settlement, payments, and immutable receipts.",
};

const CAPABILITIES = [
  {
    area: "Collection centers",
    detail:
      "Centers with operating hours, business calendars, device registries, and a readiness engine — a session opens only when the center can actually collect.",
  },
  {
    area: "Suppliers & members",
    detail:
      "Supplier profiles, documents, bank accounts, signed QR identity cards, and bulk import — a member is identified in seconds at 5 a.m. with a queue waiting.",
  },
  {
    area: "Milk collection",
    detail:
      "Readiness-gated collection sessions feeding an immutable transaction engine. A completed transaction never changes; corrections are new records.",
  },
  {
    area: "Pricing",
    detail:
      "Versioned rate cards with an approval workflow, configurable quality-band matrices, exactly-one-band resolution, and decimal-exact calculation with a full trace on every price.",
  },
  {
    area: "Settlement",
    detail:
      "Supplier, center, and period payables built from server-verified calculation records — draft, calculated, then finalized and immutable, with history-preserving cancellation.",
  },
  {
    area: "Payments & receipts",
    detail:
      "Payments against finalized settlements with allocation lines, retries, and outstanding balances — and immutable proof-of-payment receipts generated from completed payments.",
  },
  {
    area: "Sales & distribution",
    detail:
      "Customers, delivery plans and standing orders, an automated daily delivery scheduler, invoices, customer statements, and receivables.",
  },
  {
    area: "Offline sync",
    detail:
      "Operations captured offline replay idempotently — safe across retries and batches, with structured conflict handling and a read-only monitor.",
  },
  {
    area: "Reporting",
    detail:
      "Live aggregation over transactional data: daily collection, quality distribution, settlement summaries, delivery reports with CSV export.",
  },
  {
    area: "Notifications",
    detail:
      "Template-driven messages per channel and language, with a delivery record for every send.",
  },
  {
    area: "Audit",
    detail: "An append-oriented audit trail of every mutation, platform-wide.",
  },
  {
    area: "Localization",
    detail:
      "An organization resolves country, currency, timezone, and languages once at onboarding. English, Swahili, Hindi, and Arabic ship today.",
  },
] as const;

const SURFACES = [
  {
    name: "Operator app",
    detail:
      "Mobile-first and offline-first, built for an operator at 5 a.m. with a queue of farmers waiting. The phone renders what the platform decided and captures what a person did — it prices nothing and never recomputes a figure.",
  },
  {
    name: "Admin portal",
    detail:
      "Web administration for the whole network: centers, suppliers, rate cards, settlements, payments, sales, reports, and platform administration.",
  },
  {
    name: "Rider & customer views",
    detail:
      "The same mobile app serves a delivery rider on a household round and a customer checking their own account — one app, routed by capability.",
  },
] as const;

const TRUST_POINTS = [
  {
    title: "Tenant isolation enforced in the database",
    detail:
      "Row-level security in PostgreSQL means a query that forgets its filter returns nothing — application filters are defence-in-depth, not the only wall.",
  },
  {
    title: "Money is exact",
    detail:
      "Prices and totals are computed in exact decimal arithmetic end to end. Floating-point money is rejected by the platform itself.",
  },
  {
    title: "Recovery is rehearsed",
    detail:
      "Backups, disaster recovery, and point-in-time restore are executed as proofs, not written as documents. A guarantee that has never run is treated as absent.",
  },
  {
    title: "Every request is traceable",
    detail:
      "One correlation id follows a request through the platform, its events, and the notifications it triggers.",
  },
] as const;

export default function ProductPage() {
  return (
    <>
      <Section className="border-b border-border/60">
        <SectionHeading
          eyebrow="Product"
          title="Every litre measured, tested, attributed, and reconciled"
          lede="For dairy organizations running collection centers — cooperatives, collectors, processors — Lacteva makes every litre's journey from member to bulk checkable, replacing paper registers with shift-controlled records that members trust and settlement can pay against."
        />
      </Section>

      <Section>
        <SectionHeading
          eyebrow="Capabilities"
          title="What the platform does today"
          lede="Everything below is built and tested — this page describes what exists, not a roadmap."
        />
        <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((cap) => (
            <div key={cap.area} className="flex flex-col gap-2">
              <h3 className="font-semibold">{cap.area}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {cap.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section tinted>
        <SectionHeading
          eyebrow="Surfaces"
          title="Mobile-first for operations, web for administration"
        />
        <div className="grid gap-6 lg:grid-cols-3">
          {SURFACES.map((surface) => (
            <div
              key={surface.name}
              className="flex flex-col gap-3 rounded-xl border border-border bg-card p-6"
            >
              <h3 className="font-semibold">{surface.name}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {surface.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <SectionHeading
          eyebrow="Built to be trusted"
          title="Boringly reliable beats impressively fragile"
          lede="A cooperative's payroll depends on this platform, so it is engineered for auditability and recovery before novelty."
        />
        <div className="grid gap-6 sm:grid-cols-2">
          {TRUST_POINTS.map((point) => (
            <div
              key={point.title}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6"
            >
              <h3 className="font-semibold">{point.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {point.detail}
              </p>
            </div>
          ))}
        </div>
        <div className="pt-10">
          <Link
            href="/request-demo"
            className="inline-flex h-11 items-center rounded-lg bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85"
          >
            See it live — request a demo
          </Link>
        </div>
      </Section>
    </>
  );
}
