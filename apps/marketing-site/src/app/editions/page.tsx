import type { Metadata } from "next";
import Link from "next/link";
import { Check, Minus } from "lucide-react";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Editions",
  description:
    "Lacteva Collect, Operations, and Enterprise — one codebase, one data model, packaged by entitlement. Compare what each edition includes.",
};

const EDITIONS = [
  {
    name: "Lacteva Collect",
    for: "Village societies, cooperatives, and chilling-center networks",
    pitch:
      "The procurement core. Replace the paper register with records members trust: collection, quality-based pricing, settlement, payments, receipts, reports — operator app and admin portal included.",
  },
  {
    name: "Lacteva Operations",
    for: "Networks and private dairies that also run the plant",
    pitch:
      "Collect plus processing and inventory — reception, tanks, quality lab, batches, production, packaging, warehouse — and sales basics: orders, dispatch, invoices.",
  },
  {
    name: "Lacteva Enterprise",
    for: "Large dairies, unions, and federations",
    pitch:
      "Operations plus finance, enterprise integration — API gateway, SSO, webhooks — analytics, SLAs, multi-entity structures, and on-premise or hybrid deployment.",
  },
] as const;

// Condensed from the 21-row matrix in docs/product/PRODUCT_STRATEGY.md §5.
const MATRIX: Array<{ feature: string; tiers: [boolean, boolean, boolean] }> = [
  { feature: "Collection centers, sessions & operator app", tiers: [true, true, true] },
  { feature: "Suppliers, QR identity & bulk import", tiers: [true, true, true] },
  { feature: "Quality-based pricing with full trace", tiers: [true, true, true] },
  { feature: "Settlement, payments & receipts", tiers: [true, true, true] },
  { feature: "Offline collection & sync", tiers: [true, true, true] },
  { feature: "Reports & CSV export", tiers: [true, true, true] },
  { feature: "Processing: reception, tanks, quality lab, batches", tiers: [false, true, true] },
  { feature: "Inventory & warehouse", tiers: [false, true, true] },
  { feature: "Sales: orders, dispatch, invoices", tiers: [false, true, true] },
  { feature: "Finance: ledger, tax, reconciliation", tiers: [false, false, true] },
  { feature: "API gateway, SSO & webhooks", tiers: [false, false, true] },
  { feature: "Multi-entity & federation structures", tiers: [false, false, true] },
  { feature: "On-premise / hybrid deployment", tiers: [false, false, true] },
];

const PRICING_PRINCIPLES = [
  {
    title: "Priced on value handled, not seats",
    detail:
      "Dairy value scales with litres, not logins. Pricing is a base subscription per edition plus volume bands — adding an operator, a viewer, or a lab technician never costs extra.",
  },
  {
    title: "Farmers never pay",
    detail:
      "No per-farmer, per-supplier, or farmer-app fees, ever. Supplier trust is the product's engine; taxing it would be self-harm.",
  },
  {
    title: "Transparent and local",
    detail:
      "Public price bands, local currency, local payment methods. A cooperative treasurer must be able to explain the Lacteva bill to their board in one sentence.",
  },
  {
    title: "Consumption pricing only where costs are consumption-shaped",
    detail:
      "Message volume and archival storage, for example. Never for core record-keeping.",
  },
] as const;

export default function EditionsPage() {
  return (
    <>
      <Section className="border-b border-border/60">
        <SectionHeading
          eyebrow="Editions"
          title="One codebase, many editions"
          lede="Packaging is entitlements, never forks. The same system grows from one village society to a federation, so the software is never the reason to re-migrate."
        />
        <div className="grid gap-6 lg:grid-cols-3">
          {EDITIONS.map((edition) => (
            <div
              key={edition.name}
              className="flex flex-col gap-3 rounded-xl border border-border bg-card p-6"
            >
              <h2 className="text-lg font-semibold">{edition.name}</h2>
              <p className="text-xs font-medium tracking-wide text-primary uppercase">
                {edition.for}
              </p>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {edition.pitch}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <SectionHeading eyebrow="Comparison" title="What each edition includes" />
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="p-4 font-semibold">Capability</th>
                <th className="p-4 text-center font-semibold">Collect</th>
                <th className="p-4 text-center font-semibold">Operations</th>
                <th className="p-4 text-center font-semibold">Enterprise</th>
              </tr>
            </thead>
            <tbody>
              {MATRIX.map((row) => (
                <tr key={row.feature} className="border-b border-border/60 last:border-0">
                  <td className="p-4 text-muted-foreground">{row.feature}</td>
                  {row.tiers.map((included, i) => (
                    <td key={i} className="p-4 text-center">
                      {included ? (
                        <Check
                          className="mx-auto size-4 text-primary"
                          aria-label="Included"
                        />
                      ) : (
                        <Minus
                          className="mx-auto size-4 text-muted-foreground/40"
                          aria-label="Not included"
                        />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="pt-4 text-sm text-muted-foreground">
          Certified integrations, plugins, and partner apps run on top of any
          edition through the Lacteva ecosystem.
        </p>
      </Section>

      <Section tinted>
        <SectionHeading
          eyebrow="Pricing"
          title="How pricing will work"
          lede="Lacteva is preparing for its first pilots; published price bands come with commercial launch. The principles behind them are already fixed."
        />
        <div className="grid gap-6 sm:grid-cols-2">
          {PRICING_PRINCIPLES.map((p) => (
            <div key={p.title} className="flex flex-col gap-2">
              <h3 className="font-semibold">{p.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {p.detail}
              </p>
            </div>
          ))}
        </div>
        <div className="pt-10">
          <Link
            href="/request-demo"
            className="inline-flex h-11 items-center rounded-lg bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85"
          >
            Talk to us about a pilot
          </Link>
        </div>
      </Section>
    </>
  );
}
