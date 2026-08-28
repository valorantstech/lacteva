"use client";

import { useEffect, useRef } from "react";
import { LockupArt, RichDropArt } from "@/components/logo";
import { cn } from "@/lib/utils";

/**
 * The Lacteva mark's reveal in the nav (LACTEVA-MARKETING-002, per the
 * LogoReveal board's three beats): the drop falls, the milk ripples, the
 * wordmark settles in — 1.4s, once per visit.
 *
 * Since LACTEVA-MARKETING-007 the lockup it reveals is the FINAL one: the
 * drop falls into the can's belly — where the brand knocks it out — and
 * beat 3 settles the owner's traced LACTEVA letterforms, not a word set in
 * the UI font. The drop is still the RICH rendering (LACTEVA-MARKETING-003)
 * — the reveal plays lit, and flipping to flat afterwards would be a
 * visible pop, so the nav mark stays rich at rest too.
 *
 * The gate is sessionStorage, so the reveal greets a visitor's first page
 * and stays out of the way for the rest of their session. The server
 * render (and therefore the no-JS page) is the static lockup. The play
 * switch is a data attribute flipped after hydration; the animations
 * themselves live in globals.css behind `[data-reveal="on"]`, so nothing
 * re-renders and the static markup is byte-identical either way.
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
      className={cn("relative flex items-center", className)}
    >
      {/* Beat 2 — it lands, milk ripples: two rings, positioned over the
          can (the leftmost 10.9% of the lockup's box, per its viewBox). */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-0 w-[10.9%]"
      >
        <span
          data-reveal-ring
          className="nav-reveal-ring absolute -inset-1 rounded-full border-[1.5px] border-primary/50 opacity-0"
        />
        <span
          data-reveal-ring
          className="nav-reveal-ring absolute inset-0.5 rounded-full border border-primary/30 opacity-0"
          style={{ "--reveal-delay": "500ms" } as React.CSSProperties}
        />
      </span>
      <LockupArt
        idPrefix="nav"
        className="h-6 w-auto sm:h-7"
        /* Beat 1 — the drop falls, lit, into the can. */
        drop={
          <g className="nav-reveal-drop">
            <RichDropArt idPrefix="nav-drop" />
          </g>
        }
        /* Beat 3 — the wordmark settles in. */
        wordClassName="nav-reveal-word"
      />
      <span className="sr-only">Lacteva</span>
    </span>
  );
}
