/**
 * One page rhythm (Design System V1).
 *
 * The audit found forty pages wrapping *themselves*, and disagreeing: three
 * different max widths (`3xl`, `6xl`, `7xl`), two padding philosophies (`p-8`
 * flat versus a `4 → 6 → 8` step), and six pages setting `min-h-screen` inside
 * a shell that is already `min-h-full`. That is most of why the product reads
 * as assembled rather than designed, and it is one component away from fixed.
 *
 * `width` exists because pages genuinely differ, and pretending otherwise
 * would be worse than the inconsistency it replaces:
 *
 *   `wide`    tables and dashboards, which want the viewport
 *   `default` the ordinary page
 *   `narrow`  forms and settings, where a long measure hurts reading
 *
 * What is NOT negotiable is the padding step and the centring, because that is
 * the part a person notices when it changes between two pages.
 *
 * Nothing here is applied by this component's existence — a page adopts it by
 * replacing its own wrapper, which is why this lands with the page batches
 * rather than with the shell.
 */

import { cn } from "@/lib/utils";

export function PageContainer({
  width = "default",
  className,
  children,
}: {
  width?: "narrow" | "default" | "wide";
  className?: string;
  children: React.ReactNode;
}) {
  const max = {
    narrow: "max-w-3xl",
    default: "max-w-6xl",
    wide: "max-w-7xl",
  }[width];

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col gap-6 p-4 sm:p-6 lg:p-8",
        max,
        className,
      )}
    >
      {children}
    </div>
  );
}
