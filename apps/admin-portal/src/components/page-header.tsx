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
    <div className="flex flex-col gap-3 border-b border-border pb-5">
      {breadcrumbs && breadcrumbs.length > 0 ? (
        <nav aria-label="Breadcrumb">
          <ol className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
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
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
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
  hint?: string;
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
