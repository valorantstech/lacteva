import type { Metadata } from "next";
import Link from "next/link";
import {
  Building2,
  Factory,
  Handshake,
  Milk,
  Truck,
  Warehouse,
} from "lucide-react";
import { CtaBand } from "@/components/cta-band";
import { ProductShot } from "@/components/product-shot";
import {
  SceneBill,
  SceneCapture,
  SceneCollect,
  SceneDeliver,
  SceneManage,
  SceneUnderstand,
} from "@/components/scenes";
import { Section, SectionHeading } from "@/components/section";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Solutions",
  description:
    "Dairy software for cooperatives, milk collection organizations, distributors, and dairy companies — one connected operations platform, fitted to how each business runs.",
  alternates: { canonical: "/solutions" },
};

/**
 * One page, six audiences, anchored — deliberately not six thin pages.
 * Each audience gets its own problem, its own capability emphasis, and
 * its own benefit; none of them may read like a template. Suitability is
 * the message: no deployment or customer-count claims anywhere.
 */
// Each audience carries the lifecycle scene that is its daily life
// (LACTEVA-MARKETING-005): the cooperative lives at the scale, the
// distributor on the round, the enterprise in roles and grants.
const AUDIENCE_SCENES = {
  "dairy-companies": SceneUnderstand,
  cooperatives: SceneCapture,
  "collection-organizations": SceneCollect,
  distributors: SceneDeliver,
  "growing-businesses": SceneBill,
  enterprise: SceneManage,
} as const;

const SOLUTIONS = [
  {
    id: "dairy-companies",
    icon: Factory,
    name: "Dairy companies",
    problem:
      "Procurement runs in one tool, distribution in another, billing in a third — and the business lives in the gaps between them. Every question that crosses a boundary (\"did the milk we bought this week cover the rounds we delivered?\") becomes somebody's reconciliation project.",
    capabilities: [
      "The full lifecycle: procurement through reporting",
      "Rate cards & supplier settlements",
      "Customers, rounds & billing",
      "Reports that read the whole operation",
    ],
    benefit:
      "One operational spine. The milk you buy and the milk you sell live in the same records, so the cross-boundary questions answer themselves — and month-end starts from records, not from collection.",
  },
  {
    id: "cooperatives",
    icon: Handshake,
    name: "Cooperatives",
    problem:
      "A cooperative runs on member trust, and paper registers make trust expensive: a weight recorded at dawn becomes a payment dispute weeks later, between parties with no shared record to check. The register lives in one person's head, and settlement season proves it.",
    capabilities: [
      "Member & supplier records with QR identity",
      "Collection sessions with quantity & quality",
      "Quality-based pricing from rate cards",
      "Settlements built from verified records, receipts for payments",
    ],
    benefit:
      "Records members can check. Every litre is recorded against the member who poured it, priced by the card everyone can see, and settled from records nobody can quietly edit — the dispute has something to check against.",
  },
  {
    id: "collection-organizations",
    icon: Milk,
    name: "Milk collection organizations",
    problem:
      "Every centre keeps its own version of the day — a register here, a spreadsheet there — so the network's operator can't answer the only question that matters while it's still answerable: how much milk, at what quality, owed to whom, today?",
    capabilities: [
      "Collection centres with sessions & operating calendars",
      "Device & operator readiness per centre",
      "Consolidated collection reporting across centres",
      "Supplier settlements across the network",
    ],
    benefit:
      "Every centre, one view, same day. Collections flow from each centre into one set of records, so volume, quality, and payables are visible across the network while the milk is still fresh.",
  },
  {
    id: "distributors",
    icon: Truck,
    name: "Milk distributors",
    problem:
      "The same round gets typed in every morning, and billing spends the month chasing what delivery already knew. When the round, the invoice, and the payment live in different places, every customer question means opening three books.",
    capabilities: [
      "Customers with agreed plans & standing orders",
      "Daily rounds generated automatically",
      "Delivery recording on the rider's phone",
      "Invoices, statements, receivables & receipts",
    ],
    benefit:
      "The round runs itself into the books. Plans become deliveries automatically, deliveries become invoice lines, and a customer's statement traces every charge to the doorstep it came from.",
  },
  {
    id: "growing-businesses",
    icon: Building2,
    name: "Growing dairy businesses",
    problem:
      "The spreadsheets that ran the business at one size are quietly breaking it at the next — but replacing everything at once feels riskier than living with the breakage.",
    capabilities: [
      "Start with the workflow that hurts most",
      "Collection, delivery, or billing first — the rest is there when you need it",
      "One platform as you add centres, routes & customers",
      "A 30-day free trial to prove it on your own operation",
    ],
    benefit:
      "Grow into the platform instead of migrating between tools. Each new centre or route joins the same system and inherits the same workflows — the software stops being the reason growth hurts.",
  },
  {
    id: "enterprise",
    icon: Warehouse,
    name: "Enterprise dairy operations",
    problem:
      "At scale, the operational problem becomes a control problem: many centres, many roles, and an audit or compliance question never far away. Visibility can't come at the price of everyone seeing everything.",
    capabilities: [
      "Roles & granular permissions across the organization",
      "Tenant isolation enforced in the database",
      "An append-only audit trail of every change",
      "Multi-country: currency, timezone & language per organization",
    ],
    benefit:
      "Control without slowing the field. Each role sees exactly its own work, every change is audited, and the records that answer an auditor are the same records that ran the operation.",
  },
] as const;

export default function SolutionsPage() {
  return (
    <>
      <Section className="border-b border-border/60">
        <SectionHeading
          as="h1"
          eyebrow="Solutions"
          title="Built for dairy businesses at every stage of growth."
          lede="The same connected platform, fitted to how your operation actually runs — whether you collect from a thousand suppliers, deliver to a thousand doorsteps, or both."
        />
        <nav aria-label="Solutions on this page" className="flex flex-wrap gap-2">
          {SOLUTIONS.map((s) => (
            <Link
              key={s.id}
              href={`#${s.id}`}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {s.name}
            </Link>
          ))}
        </nav>
      </Section>

      {SOLUTIONS.map((solution, i) => {
        const Scene = AUDIENCE_SCENES[solution.id];
        // The distributors band goes deep-ink (LACTEVA-MARKETING-008):
        // every page carries at least one ink band, and this is the one
        // with the handset capture — the proof that reads best on dark.
        const onInk = solution.id === "distributors";
        return (
          <Section
            key={solution.id}
            variant={onInk ? "ink" : i % 2 === 0 ? "default" : "tinted"}
          >
            <article
              id={solution.id}
              className="grid scroll-mt-28 gap-8 lg:grid-cols-2 lg:gap-14"
            >
              <div className="flex flex-col gap-4">
                <span className="lacteva-icon-duo" aria-hidden>
                  <solution.icon className="size-4.5" />
                </span>
                <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                  {solution.name}
                </h2>
                <p
                  className={cn(
                    "text-sm leading-relaxed",
                    onInk ? "text-ink-muted" : "text-muted-foreground",
                  )}
                >
                  {solution.problem}
                </p>
                <p className="text-sm leading-relaxed">
                  <span className="font-semibold">With Lacteva: </span>
                  {solution.benefit}
                </p>
              </div>
              <div className="flex flex-col gap-4">
                <div data-parallax="0.05">
                  <Scene />
                </div>
                <div className="lacteva-card lacteva-lift flex flex-col gap-3 rounded-xl p-6 lg:h-fit">
                  <p className="text-xs font-semibold tracking-wide text-primary uppercase">
                    What matters most here
                  </p>
                  <ul className="flex flex-col gap-2.5">
                    {solution.capabilities.map((cap) => (
                      <li
                        key={cap}
                        className="border-l-2 border-primary/40 ps-3 text-sm leading-relaxed text-muted-foreground"
                      >
                        {cap}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
            {solution.id === "distributors" ? (
              <div className="pt-10">
                <ProductShot
                  name="mobile/roundsman"
                  variant="device"
                  width={720}
                  height={1465}
                  label="Today's round on the roundsman's phone — a young dairy's honest morning"
                  className="mx-auto w-full max-w-[300px]"
                />
              </div>
            ) : null}
          </Section>
        );
      })}

      <Section>
        <CtaBand title="Not sure which fits? Start with your operation." copy="Tell us how your dairy business runs — we'll show you Lacteva on your own workflow, with a 30-day free trial or a live demo." />
      </Section>
    </>
  );
}
