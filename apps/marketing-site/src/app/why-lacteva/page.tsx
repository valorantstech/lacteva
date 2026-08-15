import type { Metadata } from "next";
import { LinkButton } from "@/components/link-button";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Why Lacteva",
  description:
    "Why organizations choose Lacteva over single-PC collection software and the paper register: checkable records, explainable pricing, and one connected operation.",
  alternates: { canonical: "/why-lacteva" },
};

const VERSUS = [
  {
    them: "Data lives on one machine at one center",
    us: "Cloud platform with offline mobile capture — every center visible in one consolidated view, in real time.",
  },
  {
    them: "Pricing math is a black box",
    us: "Every payable amount carries a resolution and calculation trace to the exact rate-card band that produced it.",
  },
  {
    them: "No audit trail, no farmer-facing transparency",
    us: "Immutable transactions, receipts for every payment, and an append-only audit of every mutation.",
  },
  {
    them: "A pricing change is a vendor site visit",
    us: "A pricing policy change is a new rate-card version, live across the network in minutes.",
  },
  {
    them: "Month-end is a reconciliation project",
    us: "Deliveries, invoices, payments, and receipts are one chain of records, so billing follows operations instead of chasing them.",
  },
] as const;

const PRINCIPLES = [
  {
    title: "Never block the milk",
    detail:
      "Perishable-first design: collection proceeds through connectivity loss, pricing gaps, and downstream failures — always.",
  },
  {
    title: "Every number is explainable",
    detail:
      "Prices, settlements, and reports carry traces back to their inputs. If we can't show the why, we don't show the number.",
  },
  {
    title: "Farmer trust is the moat",
    detail:
      "Farmers are first-class subjects of the system before they are users of it. The record has to be right, and it has to be checkable.",
  },
  {
    title: "Meet users where they are",
    detail:
      "Mobile-first operators, low-end Android, local language, intermittent networks. English, Swahili, Hindi, and Arabic ship today.",
  },
  {
    title: "Boringly reliable beats impressively fragile",
    detail:
      "A cooperative's payroll depends on us; we optimize for auditability and recovery before novelty.",
  },
  {
    title: "AI-ready before AI-powered",
    detail:
      "No machine learning is deployed today — the data discipline that enables it is. We will not claim intelligence the platform does not have.",
  },
] as const;

export default function WhyLactevaPage() {
  return (
    <>
      <Section className="border-b border-border/60">
        <SectionHeading
          as="h1"
          eyebrow="Why Lacteva"
          title="The real competitor is paper — free, offline, and trusted"
          lede="Lacteva doesn't win by out-featuring another vendor. It wins by beating the paper register at the one thing that makes paper survive: checkability. And unlike paper, it never forgets, never smudges, and adds every record up the same way twice."
        />
      </Section>

      <Section>
        <SectionHeading
          eyebrow="Versus the status quo"
          title="Beyond the single-PC register beside the scale"
          lede="Traditional collection software bundles opaque desktop programs with the vendor's hardware. Lacteva inverts that model."
        />
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {VERSUS.map((row, i) => (
            <div
              key={row.them}
              className={`grid gap-4 p-6 sm:grid-cols-2 ${i > 0 ? "border-t border-border/60" : ""}`}
            >
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  The old way
                </p>
                <p className="text-sm text-muted-foreground">{row.them}</p>
              </div>
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium tracking-wide text-primary uppercase">
                  With Lacteva
                </p>
                <p className="text-sm">{row.us}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section variant="tinted">
        <SectionHeading
          eyebrow="Principles"
          title="The rules the product is built by"
          lede="Where these principles conflict with a farmer's ability to believe the number on the screen, trust wins."
        />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {PRINCIPLES.map((p) => (
            <div
              key={p.title}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6"
            >
              <h3 className="font-semibold">{p.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {p.detail}
              </p>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-10">
          <LinkButton href="/start-free-trial">Start Free Trial</LinkButton>
          <LinkButton href="/request-demo" variant="outline">
            Book a Demo
          </LinkButton>
        </div>
      </Section>
    </>
  );
}
