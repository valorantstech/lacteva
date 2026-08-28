/**
 * The enriched mark (LACTEVA-BRAND-003, on BRAND-004's drop).
 *
 * BRAND-004 made the drop a knockout in a can, which moved it and changed
 * its size. Every number below FOLLOWED, because `mark.rich_details()`
 * derives the light from the bulb rather than writing it down: the
 * highlight and the meniscus travelled with the drop and nobody moved them.
 *
 * Same geometry as the flat mark — `tools/brand/mark.py` is still the only
 * place the drop is drawn — with light added: a body gradient running milk
 * into a cream shadow, one warm specular highlight where the light source is,
 * and a low-opacity green meniscus, which is what the inside surface of
 * liquid actually looks like.
 *
 * **The flat mark keeps the small jobs.** Favicon, launcher, the shell's
 * 20px lockup: a silhouette is the only thing that survives at 16px, and a
 * gradient there is a smudge. This rendering owns the surfaces where the mark
 * is large and the ground is dark — sign-in, and the reveal that plays over
 * it.
 *
 * Every number below comes from `tools/brand/mark.json`, and
 * `tools/brand/check_inline.py` fails the build if any of them drifts — the
 * outline AND the light, because BRAND-002 found a mark whose silhouette
 * agreed across surfaces while its highlight existed on only one of them.
 */
const DROP =
  "M32 30C36.2 35.9 39.8 40.4 39.8 44.9C39.8 49.208 36.308 52.7 32 52.7C27.692 52.7 24.2 49.208 24.2 44.9C24.2 40.4 27.8 35.9 32 30Z";

export function BrandMark({
  size = 96,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      aria-hidden
      className={className}
      width={size}
      height={(size * 1.4551).toFixed(2)}
      viewBox="24.2 30 15.6 22.7"
    >
      <defs>
        <linearGradient
          id="lacteva-milkbody"
          x1="0.2"
          y1="0.0"
          x2="0.8"
          y2="1.0"
        >
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.55" stopColor="#FDFBF4" />
          <stop offset="1" stopColor="#E4DEC9" />
        </linearGradient>
        <radialGradient
          id="lacteva-milkglow"
          cx="0.35"
          cy="0.28"
          r="0.55"
        >
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        {/* The meniscus is clipped to the drop: mapped faithfully from the
            board it runs a little past the bulb, and an unclipped tail is a
            green whisker hanging off the mark. */}
        <clipPath id="lacteva-drop">
          <path d={DROP} />
        </clipPath>
      </defs>
      <path d={DROP} fill="url(#lacteva-milkbody)" />
      <ellipse
        cx="28.781"
        cy="40.814"
        rx="3.714"
        ry="5.2"
        fill="url(#lacteva-milkglow)"
        opacity="0.9"
      />
      <path
        d="M27.543 50.719A4.705 4.705 0 0 0 31.257 54.929"
        fill="none"
        stroke="#1B5E20"
        strokeOpacity="0.18"
        strokeWidth="0.99"
        strokeLinecap="round"
        clipPath="url(#lacteva-drop)"
      />
    </svg>
  );
}
