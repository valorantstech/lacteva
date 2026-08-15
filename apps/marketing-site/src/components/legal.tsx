/**
 * Prose primitives for the legal pages (PRE-LAUNCH-002). Same design
 * system, tuned for long-form reading: comfortable measure, clear
 * heading rhythm, list support.
 *
 * `Placeholder` renders an unresolved legal fact — entity, address,
 * jurisdiction, reviewed clauses — as a visually distinct token so no
 * reviewer can mistake a draft value for a decided one. Every placeholder
 * on these pages is also listed in the PRE-LAUNCH-002 report; the pages
 * are drafts for business/legal review until all of them are resolved.
 */
export function LegalArticle({ children }: { children: React.ReactNode }) {
  return (
    <article className="mx-auto flex w-full max-w-3xl flex-col gap-8">
      {children}
    </article>
  );
}

export function LegalSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

export function P({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>
  );
}

export function Ul({ children }: { children: React.ReactNode }) {
  return (
    <ul className="flex list-disc flex-col gap-1.5 ps-5 text-sm leading-relaxed text-muted-foreground">
      {children}
    </ul>
  );
}

export function Placeholder({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded border border-dashed border-primary/50 bg-primary/5 px-1.5 py-0.5 font-mono text-[0.85em] font-medium text-foreground">
      {children}
    </span>
  );
}
