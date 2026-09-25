"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * A horizontal scroller that SAYS it scrolls (WO-96 §3).
 *
 * A wide table in an `overflow-x-auto` box is reachable on a phone, but
 * nothing tells the person so: a bill list whose amounts sit off the right
 * edge reads as a bill list with no amounts. This box draws a fade on the
 * edge that has more, so a clipped column reads as "more this way". The
 * fades are decorative and pointer-transparent; the scroller is unchanged.
 */
export function ScrollHint({
  children,
  className,
  ...rest
}: { children: ReactNode; className?: string } & Omit<
  React.HTMLAttributes<HTMLDivElement>,
  "children" | "className"
>) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState({ left: false, right: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const left = el.scrollLeft > 2;
      const right = el.scrollWidth - el.clientWidth - el.scrollLeft > 2;
      setMore((m) => (m.left === left && m.right === right ? m : { left, right }));
    };
    const t = setTimeout(measure, 0);
    el.addEventListener("scroll", measure, { passive: true });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      clearTimeout(t);
      el.removeEventListener("scroll", measure);
      ro?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <div className="relative" data-scroll-hint data-more-left={more.left} data-more-right={more.right}>
      <div ref={ref} className={cn("w-full overflow-x-auto", className)} {...rest}>
        {children}
      </div>
      {more.left ? (
        <div
          aria-hidden
          data-testid="scroll-hint-left"
          className="pointer-events-none absolute inset-y-0 start-0 w-8 bg-gradient-to-r from-background to-transparent"
        />
      ) : null}
      {more.right ? (
        <div
          aria-hidden
          data-testid="scroll-hint-right"
          className="pointer-events-none absolute inset-y-0 end-0 w-8 bg-gradient-to-l from-background to-transparent"
        />
      ) : null}
    </div>
  );
}
