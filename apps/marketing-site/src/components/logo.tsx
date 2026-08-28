import { cn } from "@/lib/utils";

/**
 * The Lacteva mark (LACTEVA-BRAND-004; decision D-2).
 *
 * A milk CAN with a drop knocked out of its belly. The geometry is generated
 * by `tools/brand/mark.py` and appears here as literal path data because an
 * inline SVG cannot import from a Python module; `tools/brand/check_inline.py` fails the build if this copy
 * and the generator ever disagree, which is how the three hand-drawn cousins
 * that existed before this are prevented from coming back.
 *
 * This component remains the single swap point for the lockup.
 *
 * BRAND-004 updated the GEOMETRY here and nothing else. The site's own
 * dressing — nav, hero, footer, tagline placement, the scenes — is WO-32's
 * work, and this file's only change was to carry the generated paths and the
 * regenerated rich numbers, mechanically, from `mark.json`.
 */

/** Generated — do not edit by hand. See tools/brand/mark.py. */
export const CAN_PATH =
  "M22 12C28.667 12 35.333 12 42 12C42 13.333 42 14.667 42 16C43.333 16 44.667 16 46 16C46 18 46 20 46 22C44.667 22 43.333 22 42 22C42 22.667 42 23.333 42 24C46 27 48 32 48 37C48 41.667 48 46.333 48 51C48 54.314 45.314 57 42 57C35.333 57 28.667 57 22 57C18.686 57 16 54.314 16 51C16 46.333 16 41.667 16 37C16 32 18 27 22 24C22 23.333 22 22.667 22 22C20.667 22 19.333 22 18 22C18 20 18 18 18 16C19.333 16 20.667 16 22 16C22 14.667 22 13.333 22 12Z";

/** Generated — do not edit by hand. See tools/brand/mark.py. */
export const MARK_PATH =
  "M32 30C36.2 35.9 39.8 40.4 39.8 44.9C39.8 49.208 36.308 52.7 32 52.7C27.692 52.7 24.2 49.208 24.2 44.9C24.2 40.4 27.8 35.9 32 30Z";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      aria-hidden="true"
      className={cn("size-8", className)}
    >
      <rect width="64" height="64" rx="17" className="fill-primary" />
      <path d={CAN_PATH} className="fill-primary-foreground" />
      {/* The drop is knocked back to the field, so it is a hole rather than
          a third colour — which is what keeps it readable at 16px. */}
      <path d={MARK_PATH} className="fill-primary" />
    </svg>
  );
}

/**
 * The RICH rendering (LACTEVA-MARKETING-003; the LogoReveal board's "this
 * rendering owns splash, login and the website"). Same geometry — MARK_PATH
 * above is still the only outline — with the light added: body gradient into
 * a cream shadow, one warm highlight, a low-opacity green meniscus. Every
 * number is generated (tools/brand/mark.json, `rich` block) and pinned by
 * check_inline.py's RICH_STOPS, because BRAND-002 found a mark whose
 * silhouette agreed across surfaces while its highlight existed on one.
 *
 * The flat mark keeps the small jobs — icon.svg and the favicon stay flat; a
 * gradient at 16px is a smudge.
 *
 * `idPrefix` must be unique per rendered instance: SVG ids are
 * document-global, and this drop appears twice on every page (nav + footer).
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

/** The rich drop alone — for dark grounds where the lit milk reads. */
export function RichDrop({
  idPrefix,
  className,
}: {
  idPrefix: string;
  className?: string;
}) {
  return (
    <svg
      viewBox="24.2 30 15.6 22.7"
      aria-hidden="true"
      className={cn("h-9 w-auto", className)}
    >
      <RichDropArt idPrefix={idPrefix} />
    </svg>
  );
}

export function Wordmark({
  className,
  rich,
}: {
  className?: string;
  /**
   * Render the lit drop instead of the field mark — pass this instance's
   * unique gradient-id prefix. Rich is for large marks on dark grounds
   * (the footer's ink band); the flat field mark keeps the small jobs.
   */
  rich?: string;
}) {
  return (
    // Text color inherits, so a dark band recolors the wordmark by setting
    // its own text class; `text-foreground` here is only the default.
    <span
      className={cn("flex items-center gap-2.5 text-foreground", className)}
    >
      {rich ? <RichDrop idPrefix={rich} /> : <LogoMark />}
      <span className="text-lg font-semibold tracking-tight">Lacteva</span>
    </span>
  );
}
