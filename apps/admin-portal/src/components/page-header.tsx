/**
 * The top of every page (DEMO-001).
 *
 * A title, a sentence saying what the page is for, and the actions that belong
 * to it. The description is not decoration: these screens move money, and an
 * operator who cannot tell a settlement from a payment will eventually pick
 * the wrong one.
 */

import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
  breadcrumbs,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-border pb-6">
      {breadcrumbs && breadcrumbs.length > 0 ? (
        <nav aria-label="Breadcrumb">
          <ol className="flex flex-wrap items-center gap-1 text-meta text-muted-foreground">
            {breadcrumbs.map((crumb, i) => (
              <li key={`${crumb.label}-${i}`} className="flex items-center gap-1">
                {crumb.href ? (
                  <a className="hover:text-foreground hover:underline" href={crumb.href}>
                    {crumb.label}
                  </a>
                ) : (
                  <span aria-current="page">{crumb.label}</span>
                )}
                {i < breadcrumbs.length - 1 ? <span aria-hidden>/</span> : null}
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-page font-semibold tracking-tight">{title}</h1>
          {description ? (
            <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}

/**
 * A divider between two groups of figures (DEMO-010).
 *
 * The dashboard now shows procurement and sales on one page, and money flows
 * the OPPOSITE WAY through each. Without a heading, "value" above "value" is
 * genuinely ambiguous — one is what the dairy owes, the other what it is owed
 * — and a dairy owner reading it wrongly is a worse outcome than a page that
 * shows less. So the split is explicit and the direction is spelled out.
 */
export function SectionHeading({
  title,
  detail,
  href,
  hrefLabel,
}: {
  title: string;
  detail?: string;
  href?: string;
  hrefLabel?: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-sm font-semibold uppercase tracking-wide">{title}</h2>
        {detail ? <p className="text-sm text-muted-foreground">{detail}</p> : null}
      </div>
      {href ? (
        <a className="text-sm underline-offset-4 hover:underline" href={href}>
          {hrefLabel ?? "View"}
        </a>
      ) : null}
    </div>
  );
}

/**
 * A single figure with its label — the dashboard's unit of currency.
 *
 * `value` is a ReactNode so a caller can pass `<Money>` and keep exact
 * decimals; this component never receives a number to format.
 */
export function StatTile({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  // DEMO-006: a hint is often an exact money figure, which must be rendered by
  // <Money> rather than interpolated into a string.
  hint?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        {icon ? (
          <span aria-hidden className="text-muted-foreground">
            {icon}
          </span>
        ) : null}
      </div>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
