import { LinkButton } from "@/components/link-button";

/**
 * The closing conversion band, shared by every marketing page so the offer
 * is worded once: a 30-day free trial set up by a person, or a demo.
 */
export function CtaBand({
  title = "Ready to connect your dairy operations?",
  copy = "Explore Lacteva with a 30-day free trial, or talk to our team about your dairy operation. We set up the environment and walk you through the first steps.",
}: {
  title?: string;
  copy?: string;
}) {
  return (
    <div className="flex flex-col items-start gap-6 rounded-2xl bg-[linear-gradient(150deg,#0C160E_0%,#0E3D14_62%,#14481E_100%)] p-10 text-ink-foreground sm:p-14">
      <h2 className="max-w-2xl text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      <p className="max-w-2xl text-base leading-relaxed text-ink-muted">
        {copy}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <LinkButton href="/start-free-trial" variant="onInk">
          Start Free Trial
        </LinkButton>
        <LinkButton
          href="/request-demo"
          className="border border-ink-foreground/30 bg-transparent text-ink-foreground hover:bg-ink-foreground/10"
        >
          Book a Demo
        </LinkButton>
      </div>
    </div>
  );
}
