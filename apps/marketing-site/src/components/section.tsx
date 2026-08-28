import { cn } from "@/lib/utils";

/**
 * Shared page rhythm. Marketing pages are long-form; every band goes
 * through these primitives so spacing, measure, and surface treatment stay
 * uniform across the site. Three surfaces: default (paper), tinted (soft
 * green-cream), ink (dark emphasis — use at most once or twice per page).
 */
export function Section({
  children,
  className,
  variant = "default",
}: {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "tinted" | "ink";
}) {
  return (
    // data-settle: ScrollMotion gives sections that start below the fold
    // a settle-in on first entry (LACTEVA-MARKETING-004). Without JS the
    // attribute is inert and the section simply renders.
    <section
      data-settle
      className={cn(
        // The band treatments live in globals.css (LACTEVA-MARKETING-008)
        // so the tinted wash, the ink 150° gradient and its echoed glow
        // are each defined exactly once. The default surface is
        // transparent on purpose: the global atmosphere shows through.
        variant === "tinted" && "lacteva-band-tinted",
        variant === "ink" && "lacteva-band-ink",
        className,
      )}
    >
      <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        {children}
      </div>
    </section>
  );
}

export function Eyebrow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "text-xs font-medium tracking-wide text-primary uppercase",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  lede,
  align = "left",
  onInk = false,
  as: Heading = "h2",
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
  align?: "left" | "center";
  onInk?: boolean;
  /** "h1" on a page's hero heading — every page needs exactly one. */
  as?: "h1" | "h2";
}) {
  return (
    <div
      className={cn(
        "mb-10 flex max-w-3xl flex-col gap-3",
        align === "center" && "mx-auto items-center text-center",
      )}
    >
      {eyebrow ? (
        <Eyebrow className={cn(onInk && "text-ink-muted")}>{eyebrow}</Eyebrow>
      ) : null}
      <Heading className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </Heading>
      {lede ? (
        <p
          className={cn(
            "text-lg leading-relaxed",
            onInk ? "text-ink-muted" : "text-muted-foreground",
          )}
        >
          {lede}
        </p>
      ) : null}
    </div>
  );
}
