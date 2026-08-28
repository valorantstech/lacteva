import { LinkButton } from "@/components/link-button";
import { TAGLINE } from "@/components/logo";

/**
 * The closing conversion band, shared by every marketing page so the offer
 * is worded once: a 30-day free trial set up by a person, or a demo. It is
 * also one of the tagline's two homes — the other is the footer, and WO-32
 * rules out any third.
 */
export function CtaBand({
  title = "Ready to connect your dairy operations?",
  copy = "Explore Lacteva with a 30-day free trial, or talk to our team about your dairy operation. We set up the environment and walk you through the first steps.",
}: {
  title?: string;
  copy?: string;
}) {
  return (
    <div className="lacteva-band-ink relative flex flex-col items-start gap-6 overflow-hidden rounded-2xl p-10 sm:p-14">
      {/* The slow milk shimmer (LACTEVA-MARKETING-008) — a decoration
          behind the words, collapsed by the reduced-motion rule. */}
      <div aria-hidden className="lacteva-shimmer-layer" />
      {/* Content sits above the shimmer layer (static siblings would
          otherwise paint below an absolutely positioned one). */}
      <div className="relative flex flex-col gap-2.5">
        <p className="text-sm font-semibold tracking-wide text-ink-foreground/80">
          {TAGLINE}
        </p>
        <h2 className="max-w-2xl text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          {title}
        </h2>
      </div>
      <p className="relative max-w-2xl text-base leading-relaxed text-ink-muted">
        {copy}
      </p>
      <div className="relative flex flex-wrap items-center gap-3">
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
