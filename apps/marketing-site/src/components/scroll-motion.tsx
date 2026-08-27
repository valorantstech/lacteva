"use client";

import { useEffect } from "react";

/**
 * Scroll settle-ins (LACTEVA-MARKETING-004). Every `Section` carries
 * `data-settle`; this component — the site's one scroll-motion wire —
 * arms the ones that start below the fold and lets each settle in (4px
 * rise + fade, ease-out-liquid, 40ms stagger between a section's direct
 * children) the first time it enters the viewport. Then it forgets them:
 * once per visit.
 *
 * Everything defensive about it is the point:
 * - the server render is fully visible, so the no-JS page never hides a
 *   word — arming happens only here, only after hydration;
 * - a section already on screen at load is never armed, so nothing that
 *   is visible ever blinks out to animate back in;
 * - reduced motion returns before touching anything;
 * - a browser without IntersectionObserver, or any error at all, leaves
 *   the page static — a decoration's failure mode must never be a page
 *   with invisible sections.
 */
export function ScrollMotion() {
  useEffect(() => {
    try {
      if (
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ) {
        return;
      }
      if (typeof IntersectionObserver !== "function") return;

      const io = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            entry.target.classList.add("settle-go");
            io.unobserve(entry.target);
          }
        },
        // Fire when the section's leading edge is properly on screen, not
        // the instant a single pixel crosses the bottom.
        { rootMargin: "0px 0px -12% 0px" },
      );

      for (const section of document.querySelectorAll("[data-settle]")) {
        const top = section.getBoundingClientRect().top;
        if (top <= window.innerHeight * 0.85) continue;
        section.classList.add("settle-armed");
        section
          .querySelectorAll(":scope > div > *")
          .forEach((child, index) => {
            (child as HTMLElement).style.setProperty(
              "--settle-delay",
              `${Math.min(index, 5) * 40}ms`,
            );
          });
        io.observe(section);
      }

      return () => io.disconnect();
    } catch {
      // Static page. Never a broken one.
    }
  }, []);

  return null;
}
