/**
 * Loading, as milk moving (Design System V1).
 *
 * The readiness audit found four pages that render nothing at all while they
 * fetch — `/routes`, `/admin/configuration`, `/admin/roles`,
 * `/admin/operations` (UX-1). A blank screen is indistinguishable from a
 * broken one, and on a slow rural connection that is most of the wait.
 *
 * This is the shared answer, so no page invents its own. The shimmer is the
 * house `lacteva-flow` timing, and `prefers-reduced-motion` stops it globally
 * without this component knowing.
 *
 * It is deliberately NOT a spinner: a skeleton shows the SHAPE of what is
 * coming, so the page does not jump when it lands.
 */
import { cn } from "@/lib/utils";

export function Skeleton({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      // Decorative: the announcement belongs to the live region of whatever is
      // loading, not to fifteen shimmering rectangles.
      aria-hidden="true"
      className={cn("lacteva-skeleton rounded-md", className)}
      {...props}
    />
  );
}

/** The common case: a table or list still arriving. */
export function SkeletonRows({
  rows = 5,
  className,
  label = "Loading…",
}: {
  rows?: number;
  className?: string;
  label?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {/* One polite announcement for the whole block. */}
      <span className="sr-only" role="status">
        {label}
      </span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton
          key={i}
          className="h-10 w-full"
          // A touch of stagger so it reads as a list filling rather than a
          // block flashing. Capped, so a long list never feels slow.
          style={{ animationDelay: `${Math.min(i, 6) * 90}ms` }}
        />
      ))}
    </div>
  );
}
