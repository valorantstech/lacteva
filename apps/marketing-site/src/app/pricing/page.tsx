import type { Metadata } from "next";
import { CalendarCheck, Network, Smartphone, TrendingUp } from "lucide-react";
import { CtaBand } from "@/components/cta-band";
import { LinkButton } from "@/components/link-button";
import { SceneCollect } from "@/components/scenes";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Start with a 30-day free trial of Lacteva, the connected dairy operations platform, or talk to our team about the right setup for your dairy operation.",
  alternates: { canonical: "/pricing" },
};

/**
 * Commercial pricing is not finalized, so this page deliberately has no
 * price cards: it sells the commercial model that is true today — a
 * 30-day trial set up by a person, then a conversation. When plans are
 * finalized, add a PLANS array + card grid between "evaluate" and the
 * CTA; the rest of the page stands as-is. claims.test.ts bans the
 * pricing promises that are still pending.
 */
const TRIAL_STEPS = [
  {
    step: "Submit your trial request",
    detail: "Tell us about your operation — what you collect, deliver, and bill today.",
  },
  {
    step: "Our team reviews your requirements",
    detail: "We look at your centres, routes, and workflows so the trial fits your business.",
  },
  {
    step: "Your Lacteva environment is prepared",
    detail: "We set it up for you and walk your team through the first steps.",
  },
  {
    step: "Explore the platform for 30 days",
    detail: "Run a real slice of your operation — a collection round, a delivery route — on Lacteva.",
  },
  {
    step: "Decide with the team",
    detail: "Talk to us about continuing after the trial, with a setup shaped to your organization.",
  },
] as const;

const EVALUATE = [
  {
    icon: Network,
    title: "Connected operations",
    detail:
      "Procurement, collection, customers, delivery, billing, payments, and reporting on one platform — the connections are what you're evaluating.",
  },
  {
    icon: TrendingUp,
    title: "Built to scale",
    detail:
      "Suitable for growing dairy operations and larger organizations — new centres, routes, and customers join the same platform.",
  },
  {
    icon: Smartphone,
    title: "Field + office",
    detail:
      "Central management and field teams on the same records, with a mobile app built for real field conditions.",
  },
  {
    icon: CalendarCheck,
    title: "30 days, your own operation",
    detail:
      "Experience Lacteva on your own workflows before making a subscription decision.",
  },
] as const;

export default function PricingPage() {
  return (
    <>
      {/* Hero — the money page carries the settlement scene */}
      <Section className="border-b border-border/60">
        <div className="grid items-center gap-10 lg:grid-cols-[1.2fr_1fr]">
          <div className="flex max-w-3xl flex-col gap-6">
            <SectionHeading
              as="h1"
              eyebrow="Pricing"
              title="Simple to start. Ready to scale."
              lede="Explore Lacteva with a 30-day free trial, or talk to our team about the right setup for your dairy operation. Subscription plans are being finalized and will be published here — until then, our team will walk you through options sized to your organization."
            />
            <div className="flex flex-wrap items-center gap-3">
              <LinkButton href="/start-free-trial">Start Free Trial</LinkButton>
              <LinkButton href="/request-demo" variant="outline">
                Book a Demo
              </LinkButton>
            </div>
          </div>
          <div data-parallax="0.05">
            <SceneCollect />
          </div>
        </div>
      </Section>

      {/* How the trial works */}
      <Section variant="tinted">
        <SectionHeading
          eyebrow="How it works today"
          title="Start with a 30-day free trial"
          lede="The trial is set up by our team, not by an automated signup — you get a working environment and a person who knows your setup."
        />
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {TRIAL_STEPS.map((item, i) => (
            <li
              key={item.step}
              className="lacteva-card lacteva-lift flex flex-col gap-2 rounded-xl p-5"
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

      {/* What you're evaluating — on the deep-ink band for rhythm */}
      <Section variant="ink">
        <SectionHeading
          onInk
          eyebrow="What you're evaluating"
          title="The platform, on your own operation"
        />
        <div className="grid gap-6 sm:grid-cols-2">
          {EVALUATE.map((item) => (
            <div
              key={item.title}
              className="lacteva-card lacteva-lift flex flex-col gap-2.5 rounded-xl p-6"
            >
              <span className="lacteva-icon-duo" aria-hidden>
                <item.icon className="size-4.5" />
              </span>
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
        <CtaBand
          title="Start with the trial. Decide with the numbers."
          copy="Run a real slice of your dairy operation on Lacteva for 30 days, or book a demo and see the whole loop live first."
        />
      </Section>
    </>
  );
}
