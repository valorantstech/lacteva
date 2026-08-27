"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { BrandMark } from "@/components/brand-mark";

/**
 * The reveal (LACTEVA-BRAND-003).
 *
 * Three beats over 1.4 seconds — the drop falls, milk ripples, the wordmark
 * settles — played over the sign-in page, which is the one screen in this
 * product nobody is waiting on.
 *
 * **It is decoration over a working form, never a gate in front of one.** The
 * page renders and its inputs are live from the first frame; this mounts on
 * top of them. The overlay does not capture pointer events at all
 * (`pointer-events-none` on the visuals), so a click lands on whatever field
 * it was aimed at AND dismisses the reveal — a person who came to sign in
 * never pays for the animation.
 *
 * **Once a session.** `sessionStorage`, deliberately, not `localStorage`: a
 * reveal that plays once and then never again for months stops being the
 * product's welcome and becomes a thing somebody saw once. A session is the
 * unit "I came back to Lacteva".
 *
 * **Reduced motion renders nothing.** The static rich mark is already in the
 * page's own header, so a person who asked not to have animation gets the
 * same mark, still, with no overlay to dismiss — rather than a motionless
 * layer they have to tap through.
 */
const KEY = "lacteva.reveal.played";

/** The three beats, and what the last one has to wait for. */
export const REVEAL_MS = 1400;

/** Whether the reveal may play at all, given a store and a motion preference. */
export function shouldReveal(
  store: Pick<Storage, "getItem"> | null,
  reducedMotion: boolean,
): boolean {
  if (reducedMotion) return false;
  if (!store) return true;
  try {
    return store.getItem(KEY) !== "1";
  } catch {
    // A browser that refuses storage (private mode, blocked site data) still
    // gets a working sign-in page. Playing every time beats failing to render.
    return true;
  }
}

/** Nothing to subscribe to — see [useHydrated]. */
const NEVER = () => () => {};

/**
 * False while the server renders, true once the client has taken over.
 *
 * `useSyncExternalStore` with two snapshots is React's own answer to "am I
 * hydrated", and it is here for two reasons at once. It keeps the first
 * client render identical to the server's, so an overlay that only the
 * browser can decide on cannot cause a hydration mismatch — and it means
 * nothing in this component sets state from inside an effect, which is a rule
 * this codebase enforces because that pattern cascades renders.
 */
function useHydrated(): boolean {
  return useSyncExternalStore(
    NEVER,
    () => true,
    () => false,
  );
}

export function LoginReveal() {
  const hydrated = useHydrated();
  // Decided ONCE, by a pure read. On the server it answers false because
  // there is no window; on the client it answers for real — and `hydrated`
  // keeps that answer off the screen until after hydration, so the two agree.
  const [allowed] = useState(() => {
    if (typeof window === "undefined") return false;
    const reduced =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    return shouldReveal(window.sessionStorage, reduced);
  });
  const [dismissed, setDismissed] = useState(false);
  const playing = hydrated && allowed && !dismissed;

  useEffect(() => {
    if (!playing) return;
    try {
      window.sessionStorage.setItem(KEY, "1");
    } catch {
      // See `shouldReveal`: storage is a convenience here, not a control.
    }
    const end = () => setDismissed(true);
    const timer = window.setTimeout(end, REVEAL_MS);
    // Any pointer anywhere ends it early. The listener is passive and on the
    // window rather than on a barrier, so it observes the click without
    // standing in its way.
    window.addEventListener("pointerdown", end, { once: true, passive: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointerdown", end);
    };
  }, [playing]);

  if (!playing) return null;

  return (
    <div
      aria-hidden
      data-testid="login-reveal"
      // Nothing here is interactive and nothing here may intercept: the form
      // underneath is the point of the page.
      className="pointer-events-none fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-[image:var(--gradient-dairy)]"
    >
      <div className="relative flex size-40 items-center justify-center">
        <span className="lacteva-reveal-ring absolute inset-6 rounded-full border-[1.5px] border-on-brand-positive/35" />
        <span className="lacteva-reveal-ring lacteva-reveal-ring-late absolute inset-10 rounded-full border border-on-brand-positive/20" />
        <BrandMark size={78} className="lacteva-reveal-drop relative" />
      </div>
      <div className="lacteva-reveal-word flex flex-col items-center gap-1">
        <span className="text-page font-semibold tracking-tight text-on-brand">
          Lacteva
        </span>
        <span className="text-meta uppercase tracking-[0.14em] text-on-brand-muted">
          Every drop, accounted for
        </span>
      </div>
    </div>
  );
}
