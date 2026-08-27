/**
 * The enriched mark (LACTEVA-BRAND-003).
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
  "M30.69 13.229C32 11.1 32 11.1 33.31 13.229C35.613 19.1 38.866 24.386 43.071 29.085C46.426 34.537 45.314 41.619 40.449 45.78C35.585 49.94 28.415 49.94 23.551 45.78C18.686 41.619 17.574 34.537 20.929 29.085C25.134 24.386 28.387 19.1 30.69 13.229Z";

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
      height={(size * 1.4335).toFixed(2)}
      viewBox="19 11.63 26 37.27"
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
        cx="26.635"
        cy="29.09"
        rx="6.19"
        ry="8.667"
        fill="url(#lacteva-milkglow)"
        opacity="0.9"
      />
      <path
        d="M24.571 45.598A7.841 7.841 0 0 0 30.762 52.614"
        fill="none"
        stroke="#1B5E20"
        strokeOpacity="0.18"
        strokeWidth="1.651"
        strokeLinecap="round"
        clipPath="url(#lacteva-drop)"
      />
    </svg>
  );
}
