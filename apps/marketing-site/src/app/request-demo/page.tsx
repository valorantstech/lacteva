import type { Metadata } from "next";
import { Section, SectionHeading } from "@/components/section";
import { LeadForm } from "@/components/lead-form";

export const metadata: Metadata = {
  title: "Request a demo",
  description:
    "See Lacteva live — the whole loop from milk collection to receipt, demonstrated on a phone.",
};

export default function RequestDemoPage() {
  return (
    <Section>
      <div className="grid gap-12 lg:grid-cols-2">
        <div>
          <SectionHeading
            eyebrow="Request a demo"
            title="See the whole loop, live"
            lede="Collection to receipt, on a phone — including what happens when the network drops. Tell us a little about your organization and we will arrange it."
          />
          <ul className="flex max-w-md flex-col gap-3 text-sm leading-relaxed text-muted-foreground">
            <li>
              A demonstration takes under an hour and needs nothing installed
              on your side.
            </li>
            <li>
              Early pilot partners work directly with the engineering team
              and shape what ships next.
            </li>
            <li>We only use these details to respond to your request.</li>
          </ul>
        </div>
        <LeadForm />
      </div>
    </Section>
  );
}
