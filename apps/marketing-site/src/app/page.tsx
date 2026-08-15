import Link from "next/link";
import {
  CloudOff,
  FileSearch,
  Landmark,
  Layers,
  Network,
  ScrollText,
  Unplug,
} from "lucide-react";
import { Section, SectionHeading } from "@/components/section";

/**
 * Copy on this page is drawn from approved sources — Master/Vision and
 * docs/product/PRODUCT_STRATEGY.md — under the Marketing charter's rule:
 * "Marketing describes what exists; if the two disagree, the product wins
 * and the copy changes." No AI claims (no ML is deployed today), no
 * customer quotes or logos (there are none yet), no traction numbers.
 * claims.test.ts enforces the worst offenders mechanically.
 */

const COLLECTION_LOOP = [
  { step: "Check-in", detail: "The member is identified — QR card or search — and eligibility is confirmed before a drop is poured." },
  { step: "Quality test", detail: "A rapid test grades the milk; the grade drives the price, and the member sees it happen." },
  { step: "Weigh & record", detail: "Weight and quality become an immutable transaction the moment they are recorded." },
  { step: "Receipt", detail: "The member leaves with proof — the number on the receipt is the number settlement will pay against." },
  { step: "Settle & pay", detail: "Period payables build themselves from verified records; one run settles the whole network, and payments follow with receipts." },
] as const;

const DIFFERENTIATORS = [
  {
    icon: FileSearch,
    title: "Explainable pricing",
    detail:
      "Every payable amount carries a trace back to the exact rate-card band that produced it. If the platform can't show the why, it doesn't show the number.",
  },
  {
    icon: ScrollText,
    title: "Audit-grade records",
    detail:
      "Transactions snapshot at completion and never change. Corrections are new versions, so the history a dispute needs is always there.",
  },
  {
    icon: CloudOff,
    title: "Never blocks the milk",
    detail:
      "Collection proceeds through connectivity loss, pricing gaps, and downstream failures — always. Offline capture replays safely when the network returns.",
  },
  {
    icon: Network,
    title: "Every center, one view",
    detail:
      "Consolidated multi-center, multi-entity visibility in real time: how much milk, at what quality, owed to whom, today.",
  },
  {
    icon: Unplug,
    title: "Hardware freedom",
    detail:
      "Certified integrations with scales and analyzers, not bundles. The scale is not allowed to hold your data hostage.",
  },
  {
    icon: Layers,
    title: "Rules you configure",
    detail:
      "A pricing policy change is a new rate-card version, live across every center in minutes — not a vendor site visit.",
  },
] as const;

const EDITIONS = [
  {
    name: "Lacteva Collect",
    audience: "Village societies, cooperatives, and collection networks",
    detail:
      "The procurement core: centers, suppliers, collection sessions, quality-based pricing, settlement, payments, receipts, reports — with the operator app and admin portal.",
  },
  {
    name: "Lacteva Operations",
    audience: "Networks and processors that also run the plant",
    detail:
      "Everything in Collect, plus processing and inventory — reception, tanks, quality lab, batches, production, warehouse — and sales basics.",
  },
  {
    name: "Lacteva Enterprise",
    audience: "Large dairies, unions, and federations",
    detail:
      "Everything in Operations, plus finance, enterprise integration (APIs, SSO, webhooks), analytics, SLAs, and on-premise or hybrid deployment.",
  },
] as const;

const COMMITMENTS = [
  {
    icon: Landmark,
    title: "Farmers never pay",
    detail: "No per-farmer, per-supplier, or farmer-app fees. Ever.",
  },
  {
    icon: FileSearch,
    title: "No seat taxes",
    detail:
      "Adding an operator, a viewer, or a lab technician never costs extra. Dairy value scales with litres, not logins.",
  },
  {
    icon: ScrollText,
    title: "Your data stays yours",
    detail:
      "Supplier and farmer data is never sold or brokered — not at any price, to anyone. Tenant data is never pooled without consent.",
  },
] as const;

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <Section className="border-b border-border/60">
        <div className="flex max-w-3xl flex-col gap-6 py-6 sm:py-10">
          <p className="text-xs font-medium tracking-wide text-primary uppercase">
            Lacteva · by Phoenix Software
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
            Collect milk offline. Price it explainably. Settle it in one
            click.
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-muted-foreground">
            Lacteva digitizes the dairy value chain — from the farmer pouring
            milk at a village collection center through settlement and
            payment — for dairy businesses that today run on paper. Every
            number on the screen can be checked, because a platform that is
            right but unverifiable loses to a paper register that is
            checkable.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/request-demo"
              className="inline-flex h-11 items-center rounded-lg bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85"
            >
              Request a demo
            </Link>
            <Link
              href="/product"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-card px-6 text-sm font-medium transition-colors hover:bg-muted"
            >
              See how it works
            </Link>
          </div>
        </div>
      </Section>

      {/* Problem */}
      <Section tinted>
        <SectionHeading
          eyebrow="The problem"
          title="A weight recorded wrongly at 5 a.m. becomes a payment dispute three weeks later"
          lede="Dairy in most of the world runs on paper registers, disconnected spreadsheets, trust-based measurement, and month-end settlement disputes."
        />
        <div className="grid gap-6 sm:grid-cols-3">
          {[
            {
              title: "Milk is perishable",
              detail:
                "Any software that blocks the collection line is worse than paper. Delay is the one thing the product cannot tolerate.",
            },
            {
              title: "Milk is quality-priced",
              detail:
                "Manual fat-based price arithmetic is error-prone and opaque — and an unexplainable price erodes the trust the whole chain runs on.",
            },
            {
              title: "Milk is collected twice daily",
              detail:
                "Thousands of small suppliers, every morning and evening. Without a shared record, disputes have nothing to check against.",
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

      {/* How it works */}
      <Section>
        <SectionHeading
          eyebrow="How it works"
          title="One trustworthy loop, from member to settlement"
          lede="Every litre's journey is measured, tested, attributed, and reconciled — replacing paper registers with records that members trust and settlement can pay against."
        />
        <ol className="grid gap-4 lg:grid-cols-5">
          {COLLECTION_LOOP.map((item, i) => (
            <li
              key={item.step}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-5"
            >
              <span className="text-xs font-semibold text-primary tabular-nums">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="text-sm font-semibold">{item.step}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {item.detail}
              </p>
            </li>
          ))}
        </ol>
      </Section>

      {/* Differentiators */}
      <Section tinted>
        <SectionHeading
          eyebrow="Why it's different"
          title="Traditional software records what the machine said. Lacteva proves what everyone is owed, and why."
        />
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {DIFFERENTIATORS.map((item) => (
            <div key={item.title} className="flex flex-col gap-3">
              <item.icon className="size-5 text-primary" aria-hidden />
              <h3 className="font-semibold">{item.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* Editions */}
      <Section>
        <SectionHeading
          eyebrow="Editions"
          title="One platform that grows from a village society to a federation"
          lede="Every edition shares one codebase and one data model, so the software is never the reason to migrate again."
        />
        <div className="grid gap-6 lg:grid-cols-3">
          {EDITIONS.map((edition) => (
            <div
              key={edition.name}
              className="flex flex-col gap-3 rounded-xl border border-border bg-card p-6"
            >
              <h3 className="text-lg font-semibold">{edition.name}</h3>
              <p className="text-xs font-medium tracking-wide text-primary uppercase">
                {edition.audience}
              </p>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {edition.detail}
              </p>
            </div>
          ))}
        </div>
        <div className="pt-8">
          <Link
            href="/editions"
            className="text-sm font-medium text-primary hover:underline"
          >
            Compare editions →
          </Link>
        </div>
      </Section>

      {/* Commitments */}
      <Section tinted>
        <SectionHeading
          eyebrow="Commitments"
          title="Trust is the product, so some things are off the table"
        />
        <div className="grid gap-6 sm:grid-cols-3">
          {COMMITMENTS.map((item) => (
            <div key={item.title} className="flex flex-col gap-3">
              <item.icon className="size-5 text-primary" aria-hidden />
              <h3 className="font-semibold">{item.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* CTA */}
      <Section>
        <div className="flex flex-col items-start gap-6 rounded-2xl bg-primary p-10 text-primary-foreground sm:p-14">
          <h2 className="max-w-2xl text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
            Sellable in one demo, on a phone.
          </h2>
          <p className="max-w-2xl text-base leading-relaxed text-primary-foreground/80">
            Lacteva is preparing for its first pilots. If your organization
            collects milk from many producers and settles it on paper, we
            would like to show you the whole loop — collection to receipt —
            live.
          </p>
          <Link
            href="/request-demo"
            className="inline-flex h-11 items-center rounded-lg bg-primary-foreground px-6 text-sm font-medium text-primary transition-opacity hover:opacity-90"
          >
            Request a demo
          </Link>
        </div>
      </Section>
    </>
  );
}
