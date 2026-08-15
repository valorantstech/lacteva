import { cn } from "@/lib/utils";

/**
 * Shared page rhythm. Marketing pages are long-form; every band goes through
 * these two so spacing and measure stay uniform across the site.
 */
export function Section({
  children,
  className,
  tinted = false,
}: {
  children: React.ReactNode;
  className?: string;
  tinted?: boolean;
}) {
  return (
    <section className={cn(tinted && "bg-secondary/50", className)}>
      <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        {children}
      </div>
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  lede,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
}) {
  return (
    <div className="mb-10 flex max-w-3xl flex-col gap-3">
      {eyebrow ? (
        <p className="text-xs font-medium tracking-wide text-primary uppercase">
          {eyebrow}
        </p>
      ) : null}
      <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      {lede ? (
        <p className="text-lg leading-relaxed text-muted-foreground">{lede}</p>
      ) : null}
    </div>
  );
}
