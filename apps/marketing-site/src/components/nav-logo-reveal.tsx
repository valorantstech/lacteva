"use client";

import { useEffect, useRef } from "react";
import { MARK_PATH } from "@/components/logo";
import { cn } from "@/lib/utils";

/**
 * The Lacteva mark's reveal in the nav (LACTEVA-MARKETING-002, per the
 * LogoReveal board's three beats): the drop falls, the milk ripples, the
 * wordmark settles in — 1.4s, once per visit.
 *
 * The gate is sessionStorage, so the reveal greets a visitor's first page
 * and stays out of the way for the rest of their session. The server
 * render (and therefore the no-JS page) is the static lockup — the same
 * markup `Wordmark` produces, drawn from the same generated MARK_PATH so
 * the brand contract still holds one geometry. The play switch is a data
 * attribute flipped after hydration; the animations themselves live in
 * globals.css behind `[data-reveal="on"]`, so nothing re-renders and the
 * static markup is byte-identical either way.
 */

const SEEN_KEY = "lacteva-nav-reveal";

function shouldPlay(): boolean {
  try {
    if (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return false;
    }
    if (window.sessionStorage.getItem(SEEN_KEY)) return false;
    window.sessionStorage.setItem(SEEN_KEY, "1");
    return true;
  } catch {
    // No storage means no once-only gate — better never than every page.
    return false;
  }
}

export function NavLogoReveal({ className }: { className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (ref.current && shouldPlay()) ref.current.dataset.reveal = "on";
  }, []);

  return (
    <span
      ref={ref}
      data-reveal="off"
      className={cn("flex items-center gap-2.5 text-foreground", className)}
    >
      <span className="relative flex size-8 items-center justify-center">
        {/* Beat 2 — it lands, milk ripples: two rings. */}
        <span
          data-reveal-ring
          className="nav-reveal-ring pointer-events-none absolute -inset-1 rounded-full border-[1.5px] border-primary/50 opacity-0"
        />
        <span
          data-reveal-ring
          className="nav-reveal-ring pointer-events-none absolute inset-0.5 rounded-full border border-primary/30 opacity-0"
          style={{ "--reveal-delay": "500ms" } as React.CSSProperties}
        />
        <svg viewBox="0 0 64 64" aria-hidden="true" className="size-8">
          <rect width="64" height="64" rx="17" className="fill-primary" />
          {/* Beat 1 — the drop falls. */}
          <path d={MARK_PATH} className="nav-reveal-drop fill-primary-foreground" />
        </svg>
      </span>
      {/* Beat 3 — the wordmark settles in. */}
      <span className="nav-reveal-word text-lg font-semibold tracking-tight">
        Lacteva
      </span>
    </span>
  );
}
