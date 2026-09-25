import type { Metadata } from "next";

/**
 * The Open Graph fields every page carries (WO-99).
 *
 * Next.js merges metadata SHALLOWLY: a page's `openGraph` object replaces
 * the layout's rather than merging into it. So the layout cannot be the
 * place these live — a page that adds its own `url` silently drops
 * `siteName`, `type` and `locale`, which is what live served after WO-76.
 * Every page builds its `openGraph` from here, with its own `url`.
 */
export const baseOpenGraph = {
  siteName: "Lacteva",
  type: "website",
  locale: "en_IN",
  // The brand card, resolved against `metadataBase`. Named here rather than
  // inherited from the root's file-based image, because a page-level
  // `openGraph` replaces that inheritance too: a local production build
  // served og:image on the home page only. The same 1200×630 artwork.
  images: [{ url: "/opengraph-image.png", width: 1200, height: 630, alt: "Lacteva — connected dairy operations" }],
} satisfies NonNullable<Metadata["openGraph"]>;

/** A page's Open Graph block: the shared fields plus its own canonical path. */
export function pageOpenGraph(url: string): NonNullable<Metadata["openGraph"]> {
  return { ...baseOpenGraph, url };
}
