import type { Metadata } from "next";
import { LinkButton } from "@/components/link-button";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Company",
  description:
    "Lacteva is the flagship product of Phoenix Software — on a mission to digitize the entire dairy value chain for businesses that today run on paper.",
};

const WHO = [
  {
    title: "Who buys it",
    detail:
      "Dairy cooperatives and unions, private chilling-center networks, mid-size dairies and processors — organizations that buy milk from many small producers.",
  },
  {
    title: "Who uses it daily",
    detail:
      "Collection-center operators, field staff, quality labs, accountants, and managers — often at 5 a.m., with a queue waiting.",
  },
  {
    title: "Who it protects",
    detail:
      "Farmers and suppliers. Their milk, quality, and payment are recorded whether or not they ever open an app — so the record has to be right, and it has to be something they can check.",
  },
] as const;

export default function CompanyPage() {
  return (
    <>
      <Section className="border-b border-border/60">
        <SectionHeading
          as="h1"
          eyebrow="Company"
          title="Lacteva is the flagship product of Phoenix Software"
          lede="Our mission: digitize the entire dairy value chain — from the farmer pouring milk at a village collection center through processing, settlement, and market intelligence — for dairy businesses that today run on paper."
        />
      </Section>

      <Section>
        <SectionHeading eyebrow="Who it's for" title="Built for the whole chain" />
        <div className="grid gap-6 lg:grid-cols-3">
          {WHO.map((item) => (
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

      <Section variant="tinted">
        <SectionHeading
          eyebrow="Why fair records matter"
          title="Steps one and two are what a customer buys. Step three is the long game."
        />
        <ol className="flex max-w-3xl flex-col gap-6">
          {[
            "Accurate weights and quality readings make fair pricing possible.",
            "Fair pricing — and a farmer's ability to verify it — builds trust and retention.",
            "The resulting data enables credit, breeding, nutrition, and market decisions that no participant in the chain can make today.",
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-4">
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground tabular-nums">
                {i + 1}
              </span>
              <p className="text-base leading-relaxed">{step}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section>
        <SectionHeading
          eyebrow="How we build"
          title="Every production guarantee must be executable"
          lede="Lacteva is built under the Phoenix Software Engineering Standard: guarantees are proven by running them, not by writing them down. Backups restore, recovery is rehearsed, and a test that never ran counts as absent. Ambitious on scope — the long-term vision is a dairy platform serving businesses across fifty-plus countries — and deliberately conservative on claims: this page describes what exists."
        />
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <LinkButton href="/start-free-trial">Start Free Trial</LinkButton>
          <LinkButton href="/request-demo" variant="outline">
            Book a Demo
          </LinkButton>
        </div>
      </Section>
    </>
  );
}
