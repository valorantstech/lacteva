"use client";

import { useEffect } from "react";

/**
 * The site's one scroll-motion wire.
 *
 * Scroll settle-ins (LACTEVA-MARKETING-004): every `Section` carries
 * `data-settle`; this component arms the ones that start below the fold
 * and lets each settle in (4px rise + fade, ease-out-liquid, 40ms stagger
 * between a section's direct children) the first time it enters the
 * viewport. Then it forgets them: once per visit.
 *
 * Gentle parallax (LACTEVA-MARKETING-008): an element carrying
 * `data-parallax` — the illustrated scenes on their colour bands — drifts
 * a few pixels against the scroll, transform-only, clamped to ±14px so it
 * reads as depth rather than as movement. The factor is the attribute's
 * value (default 0.05).
 *
 * Everything defensive about it is the point:
 * - the server render is fully visible, so the no-JS page never hides a
 *   word — arming happens only here, only after hydration;
 * - a section already on screen at load is never armed, so nothing that
 *   is visible ever blinks out to animate back in;
 * - reduced motion returns before touching anything — no settle, no
 *   parallax;
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

      // — Parallax. Each item remembers what it has applied, because
      // getBoundingClientRect measures the transformed box: subtracting
      // the applied offset recovers the layout position, so the drift
      // never feeds back into its own measurement.
      const drifters = [...document.querySelectorAll<HTMLElement>("[data-parallax]")].map(
        (el) => ({
          el,
          factor: Number(el.dataset.parallax) || 0.05,
          applied: 0,
        }),
      );
      let raf = 0;
      const drift = () => {
        raf = 0;
        const mid = window.innerHeight / 2;
        for (const item of drifters) {
          const rect = item.el.getBoundingClientRect();
          const centre = rect.top + rect.height / 2 - item.applied;
          const offset =
            Math.round(
              Math.max(-14, Math.min(14, (mid - centre) * item.factor)) * 2,
            ) / 2;
          if (offset === item.applied) continue;
          item.applied = offset;
          item.el.style.transform = `translateY(${offset}px)`;
        }
      };
      const onScroll = () => {
        if (!raf) raf = requestAnimationFrame(drift);
      };
      if (drifters.length) {
        window.addEventListener("scroll", onScroll, { passive: true });
        drift();
      }

      return () => {
        io.disconnect();
        window.removeEventListener("scroll", onScroll);
        if (raf) cancelAnimationFrame(raf);
      };
    } catch {
      // Static page. Never a broken one.
    }
  }, []);

  return null;
}
