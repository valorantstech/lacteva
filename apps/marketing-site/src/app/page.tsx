import {
  Banknote,
  Building2,
  CalendarClock,
  ClipboardList,
  Factory,
  FileSpreadsheet,
  FileText,
  Globe2,
  Handshake,
  Landmark,
  LineChart,
  Lock,
  Milk,
  Network,
  Route,
  ShieldCheck,
  Smartphone,
  Truck,
  UserCog,
  Users,
  Warehouse,
} from "lucide-react";
import type { Metadata } from "next";
import type { CSSProperties } from "react";
import { CtaBand } from "@/components/cta-band";
import { HeroMilk } from "@/components/hero-milk";
import { LifecycleFlow } from "@/components/lifecycle-flow";
import { LinkButton } from "@/components/link-button";
import { ProductShot } from "@/components/product-shot";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

/**
 * MKT-004C homepage: the connected dairy operations story, in the order
 * the owner's specification fixes. Copy discipline is binding — every
 * capability named here is shipped and tested in the platform; the rules
 * are enforced mechanically by claims.test.ts ("marketing describes what
 * exists"). No statistics, no ROI, no superlatives, no instant-provisioning
 * language: the trial is fulfilled by a person, and the copy says so.
 */

/**
 * The living hero (LACTEVA-MARKETING-002): the approved MarketingHero board,
 * built alive. Copy is the board's, with one ruled substitution — the board's
 * secondary CTA "Watch the counter flow" has nothing real to open, so per the
 * work order it ships as "See how it works" linking to /product. The board
 * has no trial small-print; the honesty line stays anyway, because the trial
 * being set up by a person is a claim-discipline fact, not a decoration.
 *
 * The entrance is orchestrated in CSS (badge → headline lines → subhead →
 * CTAs → proof row) on the DS ease-out-liquid tokens, so it also runs on the
 * no-JS page and collapses to an instant under prefers-reduced-motion.
 */
const enter = (ms: number) =>
  ({ "--enter-delay": `${ms}ms` }) as CSSProperties;

const HERO_PROOF = [
  { fact: "Offline-first", note: "no signal, no lost milk" },
  { fact: "FAT-banded rates", note: "your chart, applied exactly" },
  { fact: "Parchi to payment", note: "one connected ledger" },
] as const;

const HERO_MODULES = [
  "Collection",
  "Quality",
  "Pricing",
  "Settlement",
  "Delivery",
  "Invoices",
  "Reports",
] as const;

const PROBLEMS = [
  {
    icon: ClipboardList,
    title: "Paper registers",
    detail: "Collection lives in a book at one centre, readable by one person, reconcilable by nobody.",
  },
  {
    icon: FileSpreadsheet,
    title: "Disconnected spreadsheets",
    detail: "Procurement, deliveries, and billing each keep their own version of the truth.",
  },
  {
    icon: Network,
    title: "Separate systems",
    detail: "A collection tool here, a billing tool there — and nothing that carries a litre from one to the other.",
  },
  {
    icon: UserCog,
    title: "Manual coordination",
    detail: "Every handover between procurement, delivery, and finance is a phone call or a walk across the yard.",
  },
  {
    icon: CalendarClock,
    title: "Repeated work",
    detail: "The same round typed in every morning; the same figures re-entered at month-end.",
  },
  {
    icon: LineChart,
    title: "Delayed visibility",
    detail: "How much milk, at what quality, owed to whom, today? The answer arrives weeks later, if at all.",
  },
] as const;

const CAPABILITY_GROUPS = [
  {
    name: "Procure",
    tagline: "Buy milk with records both sides trust",
    items: ["Suppliers", "Collection centres", "Milk collection", "Quantity & quality (FAT)", "Rate cards"],
  },
  {
    name: "Operate",
    tagline: "Run the organization, not just the data",
    items: ["Organizations", "Users & roles", "Permissions", "Notifications", "Operational workflows"],
  },
  {
    name: "Serve",
    tagline: "Know every customer and every round",
    items: ["Customers", "Delivery plans", "Daily deliveries", "Mobile field operations"],
  },
  {
    name: "Bill",
    tagline: "Money follows the milk, automatically traceable",
    items: ["Billing", "Receivables", "Payments", "Receipts", "Settlements"],
  },
  {
    name: "Understand",
    tagline: "One place where the numbers agree",
    items: ["Reports", "Operational visibility", "Financial visibility"],
  },
] as const;

const HOW_IT_WORKS = [
  { step: "Capture", detail: "Milk collection and procurement information, recorded where it happens." },
  { step: "Manage", detail: "Suppliers, customers, rate cards, and day-to-day operations." },
  { step: "Deliver", detail: "Delivery plans and daily rounds for every customer." },
  { step: "Bill", detail: "Billing and receivables built from delivery records." },
  { step: "Collect", detail: "Payments, receipts, and supplier settlements." },
  { step: "Understand", detail: "Reports and business visibility across the whole operation." },
] as const;

const AUDIENCES = [
  {
    icon: Factory,
    name: "Dairy companies",
    detail: "Procurement, distribution, and billing on one operational spine.",
  },
  {
    icon: Handshake,
    name: "Cooperatives",
    detail: "Member collection and settlement with records members can check.",
  },
  {
    icon: Milk,
    name: "Milk collection organizations",
    detail: "Centres, sessions, and quality-based pricing under one roof.",
  },
  {
    icon: Truck,
    name: "Milk distributors",
    detail: "Customers, routes, daily rounds, and the bills that follow them.",
  },
  {
    icon: Building2,
    name: "Growing dairy businesses",
    detail: "Start with the workflow that hurts most; the rest is already there.",
  },
  {
    icon: Warehouse,
    name: "Enterprise dairy operations",
    detail: "Multi-centre visibility and role-based control, built multi-tenant from day one.",
  },
] as const;

const OUTCOMES = [
  {
    title: "Better operational visibility",
    detail: "Collection, delivery, and billing answer from the same records, while the day is still happening.",
  },
  {
    title: "Less manual coordination",
    detail: "Handovers between procurement, delivery, and finance travel with the record, not with a phone call.",
  },
  {
    title: "Connected records",
    detail: "A litre collected, delivered, billed, and paid is one chain — not four entries to reconcile.",
  },
  {
    title: "More consistent workflows",
    detail: "Every centre and every round follows the same steps, so the operation behaves the same everywhere.",
  },
  {
    title: "Billing and payment clarity",
    detail: "Who owes what, and why — every invoice traces to the deliveries that produced it.",
  },
  {
    title: "Easier scaling",
    detail: "A new centre, route, or customer joins the same platform — not a new system to stitch in.",
  },
] as const;

const TRUST_POINTS = [
  {
    icon: Lock,
    title: "Tenant isolation, enforced in the database",
    detail: "Every organization's data is isolated with database-level row security, not just application filters.",
  },
  {
    icon: ShieldCheck,
    title: "Role-based access",
    detail: "A permission registry governs every action; users see and do exactly what their role allows.",
  },
  {
    icon: FileText,
    title: "Audited changes",
    detail: "Every mutation lands in an append-only audit trail, and completed transactions are immutable.",
  },
  {
    icon: Landmark,
    title: "Recovery that is rehearsed",
    detail: "Backups and restore paths are executed as proofs, not written as documents.",
  },
] as const;

export default function HomePage() {
  return (
    <>
      {/* 1 — The living hero (board: MarketingHero) */}
      <section className="relative overflow-hidden bg-[linear-gradient(150deg,#0C160E_0%,#0E3D14_62%,#14481E_100%)] text-[#FDFBF4]">
        {/* The warm glow behind the milk. Two-column layouts only: on a
            phone its 560px square hangs past the viewport and mobile
            Chrome shrinks the whole layout to fit it. */}
        <div
          aria-hidden
          className="pointer-events-none absolute top-[90px] right-[-80px] hidden size-[560px] rounded-full bg-[radial-gradient(circle_at_40%_32%,rgba(253,251,244,0.10),rgba(253,251,244,0)_60%)] lg:block"
        />
        <div className="relative mx-auto grid w-full max-w-6xl items-center gap-x-10 gap-y-12 px-4 pt-14 pb-10 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pt-20 lg:pb-14 lg:px-8">
          <div className="flex max-w-2xl flex-col gap-6">
            <div className="hero-enter flex items-center gap-2.5">
              <span className="size-2 rounded-full bg-[#7FD495]" aria-hidden />
              <p className="text-[13px] font-semibold tracking-[0.1em] text-[#90E0A5] uppercase">
                The dairy platform for milk that moves
              </p>
            </div>
            <h1 className="text-[2.6rem] leading-[1.04] font-bold tracking-[-0.03em] text-balance sm:text-6xl lg:text-[62px]">
              <span className="hero-enter block" style={enter(80)}>
                Every drop,
              </span>
              <span className="hero-enter block" style={enter(160)}>
                accounted for.
              </span>
            </h1>
            <p
              className="hero-enter max-w-[480px] text-lg leading-[1.55] text-[#C9D8BE]"
              style={enter(280)}
            >
              From the farmer&apos;s can to the customer&apos;s doorstep —
              collection, quality, pricing, settlement and delivery, priced by
              the platform and honest to the paisa. Built for the counter,
              offline-first.
            </p>
            <div
              className="hero-enter flex flex-wrap items-center gap-3.5"
              style={enter(400)}
            >
              <LinkButton
                href="/start-free-trial"
                className="rounded-xl bg-[#FDFBF4] font-bold text-[#0E3D14] hover:bg-white"
              >
                Start your dairy&apos;s trial
              </LinkButton>
              <LinkButton
                href="/product"
                className="rounded-xl border-[1.5px] border-[rgba(253,251,244,0.35)] bg-transparent font-semibold text-[#FDFBF4] hover:bg-[rgba(253,251,244,0.08)]"
              >
                See how it works
              </LinkButton>
            </div>
            <p className="hero-enter text-sm text-[#9DAB99]" style={enter(480)}>
              30-day free trial — our team sets up your environment.
            </p>
            <div
              className="hero-enter flex flex-wrap gap-x-6 gap-y-4 border-t border-[rgba(253,251,244,0.14)] pt-5"
              style={enter(560)}
            >
              {HERO_PROOF.map((item) => (
                <div key={item.fact} className="flex flex-col gap-px">
                  <div className="text-xl font-bold">{item.fact}</div>
                  <div className="text-[12.5px] text-[#9DAB99]">{item.note}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="hero-enter" style={enter(200)}>
            <HeroMilk />
          </div>
        </div>
        <div className="relative mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-3.5 gap-y-2.5 px-4 pb-8 sm:px-6 lg:px-8">
          <span className="hero-enter text-[12.5px] text-[#9DAB99]" style={enter(680)}>
            Runs the whole dairy:
          </span>
          <div className="hero-enter flex flex-wrap gap-2" style={enter(720)}>
            {HERO_MODULES.map((module) => (
              <span
                key={module}
                className="rounded-full border border-[rgba(253,251,244,0.22)] px-3 py-1 text-xs text-[#C9D8BE]"
              >
                {module}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* 2 — Problem */}
      <Section variant="tinted">
        <SectionHeading
          eyebrow="The problem"
          title="Dairy operations shouldn't live in disconnected systems."
          lede="Most dairy businesses run on pieces that don't talk to each other — and every gap between them is filled by somebody's evening."
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PROBLEMS.map((item) => (
            <div
              key={item.title}
              className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/60 p-5"
            >
              <item.icon className="size-5 text-muted-foreground" aria-hidden />
              <h3 className="text-sm font-semibold">{item.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
        <p className="pt-8 text-sm font-medium text-primary">
          There is another way to run it — as one connected operation. ↓
        </p>
      </Section>

      {/* 3 — Signature lifecycle */}
      <Section variant="ink">
        <SectionHeading
          onInk
          eyebrow="The Lacteva lifecycle"
          title="One platform. Connected dairy operations."
          lede="From the supplier's milk to the customer's bill to the settlement that pays for it — one flow, one set of records."
        />
        <LifecycleFlow />
      </Section>

      {/* 4 — Capability groups */}
      <Section>
        <SectionHeading
          eyebrow="Capabilities"
          title="Everything your dairy team needs to operate."
          lede="Five areas of the business, one platform underneath them."
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {CAPABILITY_GROUPS.map((group) => (
            <div
              key={group.name}
              className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5"
            >
              <div>
                <h3 className="font-semibold">{group.name}</h3>
                <p className="pt-1 text-xs leading-relaxed text-muted-foreground">
                  {group.tagline}
                </p>
              </div>
              <ul className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
                {group.items.map((item) => (
                  <li key={item} className="text-sm text-muted-foreground">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      {/* 5 — How it works */}
      <Section variant="tinted">
        <SectionHeading
          eyebrow="How it works"
          title="Connect the flow of your dairy business."
          lede="The lifecycle shows what is connected; this is how your team runs a day through it."
        />
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {HOW_IT_WORKS.map((item, i) => (
            <li
              key={item.step}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-5"
            >
              <span className="text-xs font-semibold text-primary tabular-nums">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="font-semibold">{item.step}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {item.detail}
              </p>
            </li>
          ))}
        </ol>
      </Section>

      {/* 6 — Who it's for */}
      <Section>
        <SectionHeading
          eyebrow="Who it's for"
          title="Built for dairy businesses at every stage of growth."
        />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {AUDIENCES.map((audience) => (
            <div key={audience.name} className="flex flex-col gap-2">
              <audience.icon className="size-5 text-primary" aria-hidden />
              <h3 className="font-semibold">{audience.name}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {audience.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* 7 — Product proof */}
      <Section variant="tinted">
        <SectionHeading
          eyebrow="The product"
          title="See Lacteva in action."
          lede="Screens from the Lacteva platform, running on demonstration data."
        />
        <div className="grid gap-6">
          <ProductShot
            name="deliveries"
            label="Daily delivery report — per-customer rounds, volumes, and values"
          />
          <div className="grid gap-6 lg:grid-cols-2">
            <ProductShot
              name="transactions"
              label="Milk collection — sessions and immutable transactions"
            />
            <ProductShot
              name="billing"
              label="Billing — invoices, receivables, and customer statements"
            />
          </div>
        </div>
      </Section>

      {/* 8 — Office + field */}
      <Section>
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div className="flex flex-col gap-4">
            <SectionHeading
              eyebrow="Office + field"
              title="Connect the office with the field."
              lede="Central operations and field teams work from the same records — what the office plans, the field executes; what the field records, the office sees."
            />
            <ul className="flex flex-col gap-3">
              {[
                { icon: Smartphone, text: "A mobile app for collection operators, delivery riders, and customers — one app, routed by what each person is allowed to do." },
                { icon: Route, text: "The day's round on the rider's phone; the day's report on the manager's screen — the same deliveries." },
                { icon: Globe2, text: "Built for real field conditions: operations captured offline replay safely when the network returns." },
              ].map((item, i) => (
                <li key={i} className="flex items-start gap-3">
                  <item.icon className="mt-0.5 size-4.5 shrink-0 text-primary" aria-hidden />
                  <span className="text-sm leading-relaxed text-muted-foreground">
                    {item.text}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <ProductShot
            name="mobile-operator"
            label="Lacteva mobile app — field operations"
          />
        </div>
      </Section>

      {/* 9 — Automation */}
      <Section variant="tinted">
        <SectionHeading
          eyebrow="Automation"
          title="Spend less time repeating the same operational work."
          lede="Lacteva automates the work that is the same every day — and leaves the decisions to people."
        />
        <div className="grid gap-6 lg:grid-cols-3">
          {[
            {
              title: "Daily rounds, generated",
              detail: "Standing orders and delivery plans become each day's deliveries automatically, on your business day, in your timezone — and never twice.",
            },
            {
              title: "Month-end bills, drafted",
              detail: "Invoices are drafted from the month's delivery records automatically. A person reviews and issues them — drafts move nobody's balance.",
            },
            {
              title: "Notifications, templated",
              detail: "Messages go out from a template registry per channel and language, with a delivery record for every send.",
            },
          ].map((item) => (
            <div
              key={item.title}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6"
            >
              <h3 className="font-semibold">{item.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* 10 — Outcomes */}
      <Section>
        <SectionHeading
          eyebrow="Outcomes"
          title="More connected operations. Better visibility."
        />
        <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
          {OUTCOMES.map((outcome) => (
            <div key={outcome.title} className="flex flex-col gap-2">
              <h3 className="font-semibold">{outcome.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {outcome.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* 11 — International readiness */}
      <Section variant="tinted">
        <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr] lg:items-center">
          <SectionHeading
            eyebrow="International"
            title="Designed for dairy businesses across markets."
            lede="Your organization sets its country once — currency, timezone, and languages follow."
          />
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { icon: Globe2, text: "Multi-country: an organization resolves country, currency, and timezone at onboarding." },
              { icon: Banknote, text: "Local currency on every amount, with exact decimal arithmetic underneath." },
              { icon: CalendarClock, text: "Timezone-aware business dates — a 5 a.m. round belongs to your day, not the server's." },
              { icon: Users, text: "Localized for the team: English, Swahili, Hindi, and Arabic ship today." },
            ].map((item, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4">
                <item.icon className="mt-0.5 size-4.5 shrink-0 text-primary" aria-hidden />
                <span className="text-sm leading-relaxed text-muted-foreground">
                  {item.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* 12 — Trust */}
      <Section>
        <SectionHeading
          eyebrow="Trust & security"
          title="Built for business-critical operations."
          lede="A dairy's payroll and a customer's bill depend on these records, so the platform is engineered for isolation, auditability, and recovery first."
        />
        <div className="grid gap-6 sm:grid-cols-2">
          {TRUST_POINTS.map((point) => (
            <div
              key={point.title}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-6"
            >
              <point.icon className="size-5 text-primary" aria-hidden />
              <h3 className="font-semibold">{point.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {point.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* 13 — Final CTA */}
      <Section>
        <CtaBand />
      </Section>
    </>
  );
}
