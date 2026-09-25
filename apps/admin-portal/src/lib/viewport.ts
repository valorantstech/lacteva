"use client";

import { useEffect, useState } from "react";

/**
 * Is this a phone-width screen? (WO-96)
 *
 * The shop owner has no laptop, so below the tablet breakpoint the money
 * tables become stacked cards. Decided by `matchMedia`, not by CSS classes
 * that render both views and hide one: rendering one view keeps the DOM
 * honest (one "Amount due" on the page, not two), keeps every existing test
 * on the desktop path, and lets a test choose the phone by stubbing
 * `window.matchMedia`. Server render and environments without `matchMedia`
 * (jsdom) answer "wide", which is the desktop table.
 */
export const NARROW_QUERY = "(max-width: 767px)";

export function useIsNarrow(): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(NARROW_QUERY);
    const update = () => setNarrow(mql.matches);
    // Deferred by a tick, like every effect that sets state in this portal.
    const t = setTimeout(update, 0);
    mql.addEventListener?.("change", update);
    return () => {
      clearTimeout(t);
      mql.removeEventListener?.("change", update);
    };
  }, []);
  return narrow;
}
