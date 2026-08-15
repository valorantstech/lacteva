import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import { CtaBand } from "@/components/cta-band";
import { LifecycleFlow } from "@/components/lifecycle-flow";
import { ProductShot } from "@/components/product-shot";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Product",
  description:
    "Dairy operations software that connects procurement, collection, customers, delivery, billing, payments, settlements, and reporting in one platform.",
  alternates: { canonical: "/product" },
  openGraph: {
    title: "Lacteva — Product",
    description:
      "One connected platform for dairy operations: procurement, collection, delivery, billing, payments, and reporting.",
  },
};

/**
 * MKT-004D product page: the five capability groups sold on business
 * value, with the feature depth second. Every capability listed is
 * shipped; claims.test.ts polices the copy.
 */
const GROUPS = [
  {
    name: "Procure",
    headline: "Buy milk with records both sides of the scale trust",
    value:
      "Procurement is where dairy trust is won or lost: a weight and a quality reading taken in seconds set what a supplier is owed weeks later. Lacteva records every collection against the supplier, the centre, and the session it happened in, prices it from your rate cards by quantity and quality, and keeps the record fixed once it is made — so the number on the supplier's receipt is the number settlement pays against.",
    items: [
      "Suppliers & profiles",
      "Collection centres",
      "Collection sessions",
      "Milk collection records",
      "Quantity & quality (FAT)",
      "Rate cards & quality-based pricing",
    ],
  },
  {
    name: "Operate",
    headline: "Run the organization, not just the data",
    value:
      "An operation is people with responsibilities, not rows in a database. Lacteva models your organization with users, roles, and a permission for every action, so an operator, an accountant, and a manager each see exactly their own work — and notifications carry operational events to the people who need to act on them.",
    items: [
      "Organizations & structure",
      "Users & roles",
      "Granular permissions",
      "Notifications",
      "Operational workflows",
    ],
  },
  {
    name: "Serve",
    headline: "Know every customer and every round",
    value:
      "The delivery side runs on rhythm: the same customers, the same rounds, every day. Lacteva holds each customer's agreed plan and standing order, turns them into the day's deliveries automatically, and puts the round on the field team's phone — so serving a hundred households stops being a hundred manual entries every morning.",
    items: [
      "Customers & agreed plans",
      "Standing orders",
      "Automatically generated daily deliveries",
      "Mobile field operations",
    ],
  },
  {
    name: "Bill",
    headline: "Money follows the milk, traceably",
    value:
      "Billing built on delivery records cannot drift from what actually happened. Invoices are drafted from the period's deliveries, receivables show who owes what, payments settle against invoices with a receipt for every one — and on the procurement side, supplier settlements are built the same way, from verified collection records, exact to the decimal.",
    items: [
      "Invoices & billing",
      "Receivables & statements",
      "Payments & receipts",
      "Supplier settlements",
    ],
  },
  {
    name: "Understand",
    headline: "One place where the numbers agree",
    value:
      "When collection, delivery, and billing share one platform, reporting stops being reconciliation. Lacteva's reports aggregate the live operational records — daily collection, quality distribution, delivery rounds, settlement summaries, receivables — so the operational picture and the financial picture are the same picture.",
    items: [
      "Operational reports",
      "Financial visibility",
      "CSV export",
      "Timezone-aware business dates",
    ],
  },
] as const;

const CONNECTIONS = [
  {
    from: "A collection recorded in Procure",
    to: "becomes a supplier payable in Bill — settlements build themselves from verified collection records.",
  },
  {
    from: "A plan agreed in Serve",
    to: "becomes each day's deliveries automatically — and every delivery becomes an invoice line.",
  },
  {
    from: "A payment recorded in Bill",
    to: "becomes a receipt, an updated balance, and a settled account — with the trail to prove it.",
  },
  {
    from: "Everything, as it happens",
    to: "lands in Understand — reports read the same records the operation writes.",
  },
] as const;

export default function ProductPage() {
  return (
    <>
      {/* Hero */}
      <Section className="border-b border-border/60">
        <SectionHeading
          as="h1"
          eyebrow="Product"
          title="Everything your dairy operation needs to stay connected."
          lede="Lacteva is dairy operations software built as one platform, not a bundle of tools: procurement, collection, customers, delivery, billing, payments, settlements, and reporting share one set of records, so every part of the business works from the same truth."
        />
      </Section>

      {/* Lifecycle */}
      <Section variant="ink">
        <SectionHeading
          onInk
          eyebrow="The lifecycle"
          title="One flow, from supplier to report"
          lede="Every stage hands its records to the next — nothing is re-entered, nothing is reconciled by hand."
        />
        <LifecycleFlow />
      </Section>

      {/* Five groups */}
      <Section>
        <SectionHeading
          eyebrow="Capabilities"
          title="Five areas of the business. One platform underneath."
        />
        <div className="flex flex-col gap-12">
          {GROUPS.map((group, i) => (
            <article
              key={group.name}
              className="grid gap-6 border-t border-border pt-10 first:border-t-0 first:pt-0 lg:grid-cols-[1.2fr_1fr] lg:gap-12"
            >
              <div className="flex flex-col gap-3">
                <p className="text-xs font-semibold text-primary tabular-nums">
                  {String(i + 1).padStart(2, "0")}
                </p>
                <h3 className="text-2xl font-semibold tracking-tight">
                  {group.name}
                </h3>
                <p className="text-base font-medium">{group.headline}</p>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {group.value}
                </p>
              </div>
              <ul className="flex h-fit flex-wrap gap-2 lg:justify-end">
                {group.items.map((item) => (
                  <li
                    key={item}
                    className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </Section>

      {/* How the groups connect */}
      <Section variant="tinted">
        <SectionHeading
          eyebrow="The operational workflow"
          title="Capabilities are only half the story — the connections are the product."
        />
        <div className="grid gap-4 sm:grid-cols-2">
          {CONNECTIONS.map((c) => (
            <div
              key={c.from}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6"
            >
              <p className="flex items-center gap-2 text-sm font-semibold">
                {c.from}
                <ArrowRight className="size-4 shrink-0 text-primary" aria-hidden />
              </p>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {c.to}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* Product proof */}
      <Section>
        <SectionHeading
          eyebrow="The product"
          title="Screens from the platform"
          lede="Running on demonstration data."
        />
        <div className="grid gap-6 lg:grid-cols-2">
          <ProductShot
            name="deliveries"
            label="Daily delivery report — per-customer rounds, volumes, and values"
          />
          <ProductShot
            name="billing"
            label="Billing — invoices, receivables, and customer statements"
          />
        </div>
      </Section>

      {/* Field + office */}
      <Section variant="tinted">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <SectionHeading
              eyebrow="Web + mobile"
              title="The office administers. The field operates."
              lede="The admin portal runs the network — centres, suppliers, rate cards, settlements, billing, reports. The mobile app serves the people in the field: a collection operator, a delivery rider, and a customer each get their own experience, routed by what they are allowed to do. Work captured offline replays safely when the network returns, so the field never waits for a signal."
            />
          </div>
          <ProductShot
            name="mobile-operator"
            label="Lacteva mobile app — field operations"
          />
        </div>
      </Section>

      {/* Outcomes */}
      <Section>
        <SectionHeading
          eyebrow="Outcomes"
          title="What a connected operation gets you"
        />
        <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
          {[
            {
              title: "One version of the truth",
              detail: "Procurement, delivery, and finance answer from the same records — the meeting about whose spreadsheet is right stops happening.",
            },
            {
              title: "Work that carries itself forward",
              detail: "Collections become settlements; deliveries become invoices; payments become receipts. The handovers are the platform's job.",
            },
            {
              title: "Visibility while it still matters",
              detail: "Today's collection, today's rounds, today's receivables — while the day is still happening, not at month-end.",
            },
            {
              title: "An operation that scales by configuration",
              detail: "A new centre, route, or customer joins the same platform and inherits the same workflows.",
            },
          ].map((o) => (
            <div key={o.title} className="flex flex-col gap-2">
              <h3 className="font-semibold">{o.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {o.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* CTA */}
      <Section>
        <CtaBand title="See what connected operations feel like." />
      </Section>
    </>
  );
}
