import { cn } from "@/lib/utils";

/**
 * The Lacteva identity (LACTEVA-BRAND-004; worn here per LACTEVA-MARKETING-007).
 *
 * A milk CAN with a drop knocked out of its belly, and the owner's LACTEVA
 * wordmark — LACTE in navy, VA in the green gradient, the drop living in the
 * final A. Every path here is GENERATED: the can and drop by
 * `tools/brand/mark.py`, the letterforms traced from the binding reference by
 * `tools/brand/trace_wordmark.py` (WO-31 Amendment 1 forbids a font-rendered
 * approximation of the wordmark on any committed surface). The geometry
 * appears as literal data because an inline SVG cannot import from a Python
 * module; `tools/brand/check_inline.py` pins the can and drop, and
 * `brand-mark.test.ts` pins everything else against `mark.json` — which is
 * how the three hand-drawn cousins that once existed are kept from coming
 * back.
 *
 * This component remains the single swap point for the lockup.
 */

/** Generated — do not edit by hand. See tools/brand/mark.py. */
export const CAN_PATH =
  "M22 12C28.667 12 35.333 12 42 12C42 13.333 42 14.667 42 16C43.333 16 44.667 16 46 16C46 18 46 20 46 22C44.667 22 43.333 22 42 22C42 22.667 42 23.333 42 24C46 27 48 32 48 37C48 41.667 48 46.333 48 51C48 54.314 45.314 57 42 57C35.333 57 28.667 57 22 57C18.686 57 16 54.314 16 51C16 46.333 16 41.667 16 37C16 32 18 27 22 24C22 23.333 22 22.667 22 22C20.667 22 19.333 22 18 22C18 20 18 18 18 16C19.333 16 20.667 16 22 16C22 14.667 22 13.333 22 12Z";

/** Generated — do not edit by hand. See tools/brand/mark.py. */
export const MARK_PATH =
  "M32 30C36.2 35.9 39.8 40.4 39.8 44.9C39.8 49.208 36.308 52.7 32 52.7C27.692 52.7 24.2 49.208 24.2 44.9C24.2 40.4 27.8 35.9 32 30Z";

/** Generated — traced letterforms, LACTE. See tools/brand/trace_wordmark.py. */
export const WORDMARK_NAVY_PATH =
  "M26.5 28.23C25.54 32.3 26.16 37.25 26.17 41.5L26.2 69.5L26.2 98.5C26.22 102.44 25.64 107.04 26.5 110.77C31.08 111.33 35.87 110.98 40.5 110.99L65.5 111C72.32 111 83.28 111.99 89.5 110.54C90.04 106.27 90.24 100.73 89.5 96.48C85.07 95.58 80.08 96.02 75.5 96.07L42.5 95.94C41.11 91.5 42.05 79.86 42.05 74.5L41.99 28.5C38.4 27.16 30.51 27.69 26.5 28.23ZM140.73 28.5C138.42 31.32 137.26 34.97 135.5 38.14L123.94 60.5L105.79 95.5L98.11 110.5C101.72 111.75 111.57 111.47 115.32 110.5L127.01 87.5L147.5 47.85C150.23 49.73 151.54 54.59 153.04 57.5C157.15 65.45 161.66 73.25 165.17 81.5L164.5 82.1L160.5 82.12C154.75 82.21 148.44 81.54 142.83 82.5C139.84 86.08 138.18 91.29 136.11 95.5C138.98 96.76 143.23 96.13 146.5 96.11C154.78 96.06 164.43 95.16 172.5 96.39L179.5 110.52C183.55 111.56 193.09 111.72 197.02 110.5C193.12 101.2 187.8 92.59 183.5 83.48L174 64.5L170.17 57.5L160.27 38.5C158.76 35.26 157.3 31.24 155 28.5C151.26 27.2 144.53 27.32 140.73 28.5ZM276.5 110.55L276.5 96.47C272.97 95.72 269.16 96.07 265.5 96.07L243.5 96.07C239.6 96.08 235.34 96.53 231.5 95.71C228.68 95.12 226.06 94.02 223.5 92.79C206.53 84.6 208 50.04 227.5 44.16C233.05 42.49 238.76 42.86 244.5 42.86L264.5 42.84C268.26 42.86 272.44 43.27 276.04 42.5C276.93 38.15 276.72 32.98 276.32 28.5C270.99 26.86 262.37 27.94 256.5 27.94C240.16 27.93 225.76 25.94 211.5 35.26C189.13 49.88 191.6 90.94 213.5 104.93C225.91 112.85 241.47 111.01 255.5 111C262.25 110.99 269.96 111.93 276.5 110.55ZM289.5 28.06C288.24 31.38 288.67 38.8 289.23 42.5C291.19 43.07 293.4 42.83 295.5 42.82L317.5 42.83L318.37 43.5L318.51 110.5C321.98 111.33 330.5 111.76 333.8 110.5L333.92 63.5L333.96 43.5L334.5 42.95L353.5 42.85C356.71 42.87 360.64 43.4 363.66 42.5C364.25 38.73 364.68 31.54 363.5 28.09L289.5 28.06ZM377.5 28.05C376.13 32.56 377.04 41.4 377.05 46.5L377.06 86.5C377.06 92.09 376.09 106.39 377.5 110.86L422.5 110.99C428.51 110.99 439.95 112 445.16 110.5L445.23 96.5C441.38 95.46 436.61 96.07 432.5 96.07L407.5 96.05C402.6 96.11 397.27 96.6 392.5 95.72C391.81 91.69 391.82 80.42 392.5 76.35C397.03 75.59 401.88 75.96 406.5 75.98L429.5 75.98C433.58 75.98 438.34 76.54 442.15 75.5L442.23 62.5C438.94 61.67 435.02 62.08 431.5 62.08L406.5 62.07C401.93 62.1 396.87 62.69 392.5 61.63L392.5 43.2C397.28 42.3 402.58 42.88 407.5 42.86L444.5 42.73C445.59 39.69 445.44 31.13 444.5 28.06L377.5 28.05Z";

/** Generated — traced letterforms, VA with the drop in the A. */
export const WORDMARK_GREEN_PATH =
  "M454.99 28.5L479.82 80.5L493.83 110.5C498.01 111.92 503.93 111.03 508.5 110.97C510.96 107.62 512.43 103.34 514.04 99.5L522.35 81.5L546.99 28.5L546.5 27.89L530.5 27.93L529.85 28.5C528.37 30.51 527.5 33.16 526.63 35.5L520.83 48.5L501.5 90.81L484.29 53.5L477.47 38.5C476.01 34.95 474.49 31.28 472.5 28.05L455.5 27.94L454.99 28.5ZM568.5 28.16C565.84 32.23 563.77 36.99 561.86 41.5L553.64 58.5L528.83 110.5C533.03 111.84 540.89 111.25 545.5 110.84L568.95 61.5C571.01 56.96 572.94 52.29 575.5 48.01C578.8 52.38 581.99 60.36 584.13 65.5L594.88 87.5L605.5 110.67C609.13 111.3 619.68 111.7 622.88 110.5L617.24 98.5C611.89 85.48 604.63 73.43 599.04 60.5L583.33 28.5C579.15 27.12 572.99 27.6 568.5 28.16ZM575.5 78.3C573.21 82.64 570.67 86.92 568.9 91.5C567.17 97.17 569.69 101.67 575.5 102.86C582.46 101.58 584.83 97.72 582.5 90.77L576.5 78.6L575.5 78.3Z";

/**
 * The owner's tagline, verbatim from the artwork (mark.json `logo.taglineText`).
 * It lands in the footer and the CTA band ONLY (WO-32) — set as text rather
 * than as the traced outline, because at these sizes it is copy to read, not
 * letterform art, and Amendment 1's tracing rule binds the WORDMARK.
 */
export const TAGLINE = "Smart Dairy. Stronger Tomorrow.";

// The identity's own colours (mark.py LOGO_* — sampled from the artwork,
// never Design System tokens; the navy in particular exists nowhere else).
const LOGO_DAIRY = "#1B5E20";
const LOGO_CREAM = "#FDFBF4";
const LOGO_DEEP = "#0E3D14";
const LOGO_NAVY = "#022551";
const LOGO_VA_TOP = "#6AA227";
const LOGO_VA_BOTTOM = "#4C8C22";

// The lockup's arrangement, mechanically from mark.json's `lockup` block:
// the can scaled beside the letterforms, cropped to the caps — the tagline
// strip of the source canvas is excluded, because the tagline's two homes
// are ruled to be the footer and the CTA band, not every lockup.
const LOCKUP_VIEWBOX = "0 13.766 729.04 111.408";
const LOCKUP_CAN_TRANSFORM = "translate(0 13.766) scale(2.476) translate(-16 -12)";
const LOCKUP_WORD_TRANSFORM = "translate(106.159 0)";

/**
 * The RICH rendering (LACTEVA-MARKETING-003; the LogoReveal board's "this
 * rendering owns splash, login and the website"). Same geometry — MARK_PATH
 * above is still the only outline — with the light added: body gradient into
 * a cream shadow, one warm highlight, a low-opacity green meniscus. Every
 * number is generated (tools/brand/mark.json, `rich` block) and pinned by
 * check_inline.py's RICH_STOPS, because BRAND-002 found a mark whose
 * silhouette agreed across surfaces while its highlight existed on one.
 *
 * `idPrefix` must be unique per rendered instance: SVG ids are
 * document-global.
 */
export function RichDropArt({
  idPrefix,
  className,
}: {
  idPrefix: string;
  className?: string;
}) {
  const body = `${idPrefix}-milkbody`;
  const glow = `${idPrefix}-milkglow`;
  const clip = `${idPrefix}-drop`;
  return (
    <g className={className}>
      <defs>
        <linearGradient id={body} x1="0.2" y1="0" x2="0.8" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.55" stopColor="#FDFBF4" />
          <stop offset="1" stopColor="#E4DEC9" />
        </linearGradient>
        <radialGradient id={glow} cx="0.35" cy="0.28" r="0.55">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        {/* The meniscus is clipped to the drop: mapped faithfully from the
            board it runs a little past the bulb, and an unclipped tail is a
            green whisker hanging off the mark. */}
        <clipPath id={clip}>
          <path d={MARK_PATH} />
        </clipPath>
      </defs>
      <path d={MARK_PATH} fill={`url(#${body})`} />
      <ellipse
        cx="28.781"
        cy="40.814"
        rx="3.714"
        ry="5.2"
        fill={`url(#${glow})`}
        opacity="0.9"
      />
      <path
        d="M27.543 50.719A4.705 4.705 0 0 0 31.257 54.929"
        fill="none"
        stroke="#1B5E20"
        strokeOpacity="0.18"
        strokeWidth="0.99"
        strokeLinecap="round"
        clipPath={`url(#${clip})`}
      />
    </g>
  );
}

/**
 * The full lockup as one SVG: can + LACTEVA, in the generated arrangement.
 * `onInk` is the on-ink variant the generator also emits — cream can body,
 * deep drop, all-cream letterforms (the VA gradient would vanish on the dark
 * band, so it is not attempted there).
 *
 * `drop` lets the nav put the RICH drop in the can's belly (the reveal plays
 * lit, and flipping to flat afterwards would be a visible pop); everywhere
 * else the flat generated drop ships. `wordClassName` exists so the reveal
 * can choreograph the letterforms without a second copy of them.
 *
 * The A-drop counter in the final A is in the traced path; below ~20px of
 * cap height it stops resolving, which the reduction rules say is correct.
 */
export function LockupArt({
  idPrefix,
  onInk = false,
  drop,
  wordClassName,
  className,
}: {
  idPrefix: string;
  onInk?: boolean;
  drop?: React.ReactNode;
  wordClassName?: string;
  className?: string;
}) {
  const va = `${idPrefix}-va`;
  return (
    <svg
      viewBox={LOCKUP_VIEWBOX}
      aria-hidden="true"
      className={cn("h-8 w-auto", className)}
    >
      {onInk ? null : (
        <defs>
          {/* Vertical, y 30→108 in the letterforms' own space — verbatim
              from the generated lockup (the word group only translates in
              x, so userSpaceOnUse keeps the artwork's gradient run). */}
          <linearGradient
            id={va}
            gradientUnits="userSpaceOnUse"
            x1="0"
            y1="30"
            x2="0"
            y2="108"
          >
            <stop offset="0" stopColor={LOGO_VA_TOP} />
            <stop offset="1" stopColor={LOGO_VA_BOTTOM} />
          </linearGradient>
        </defs>
      )}
      <g transform={LOCKUP_CAN_TRANSFORM}>
        <path d={CAN_PATH} fill={onInk ? LOGO_CREAM : LOGO_DAIRY} />
        {drop ?? (
          <path d={MARK_PATH} fill={onInk ? LOGO_DEEP : LOGO_CREAM} />
        )}
      </g>
      {/* The animated class sits on an INNER group: a CSS transform from
          the reveal's keyframes would otherwise replace this group's
          transform attribute, and the word would land on the can. */}
      <g transform={LOCKUP_WORD_TRANSFORM}>
        <g className={wordClassName}>
          <path d={WORDMARK_NAVY_PATH} fill={onInk ? LOGO_CREAM : LOGO_NAVY} />
          <path
            d={WORDMARK_GREEN_PATH}
            fill={onInk ? LOGO_CREAM : `url(#${va})`}
          />
        </g>
      </g>
    </svg>
  );
}

export function Wordmark({
  className,
  onInk = false,
  idPrefix = "lockup",
}: {
  className?: string;
  /** The on-ink variant, for the footer and any other dark band. */
  onInk?: boolean;
  /** Unique per rendered instance — SVG gradient ids are document-global. */
  idPrefix?: string;
}) {
  return (
    <span className={cn("inline-flex items-center", className)}>
      <LockupArt idPrefix={idPrefix} onInk={onInk} />
      {/* The logo is a picture; the link still needs a name. */}
      <span className="sr-only">Lacteva</span>
    </span>
  );
}
