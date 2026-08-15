import type { Metadata } from "next";
import { Section, SectionHeading } from "@/components/section";
import { LeadForm } from "@/components/lead-form";

export const metadata: Metadata = {
  title: "Start your free trial",
  description:
    "Request a 30-day free trial of Lacteva — the connected dairy operations platform. Our team sets up your environment and gets you started.",
  alternates: { canonical: "/start-free-trial" },
};

/**
 * Trial request, not self-service provisioning: a person sets up the
 * environment, and the copy below says so plainly. claims.test.ts bans
 * the provisioning promises this page must never make.
 */
export default function StartFreeTrialPage() {
  return (
    <Section>
      <div className="grid gap-12 lg:grid-cols-2">
        <div>
          <SectionHeading
            as="h1"
            eyebrow="30-day free trial"
            title="Try Lacteva with your own operation"
            lede="Tell us about your dairy business and our team will set up a trial environment for you — 30 days, full platform, your own data."
          />
          <ul className="flex max-w-md flex-col gap-3 text-sm leading-relaxed text-muted-foreground">
            <li>
              We prepare the environment and walk your team through the first
              steps — you are not left alone with an empty screen.
            </li>
            <li>
              Bring one collection round or one delivery route to start;
              connecting a slice of the real operation shows more than a tour
              ever could.
            </li>
            <li>We only use these details to respond to your request.</li>
          </ul>
        </div>
        <LeadForm
          intent="trial"
          submitLabel="Request your free trial"
          successDetail="Thanks — your trial request has been received. Our team will review your requirements and help set up your Lacteva environment."
        />
      </div>
    </Section>
  );
}
