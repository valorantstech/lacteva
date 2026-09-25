import type { Metadata } from "next";

/**
 * The bill page is reachable by anyone holding its link, so the one thing it
 * must never be is FINDABLE: no index, no follow, no cache (WO-86). The
 * platform sets the same headers on the JSON; this sets them on the page.
 */
export const metadata: Metadata = {
  title: "Your bill · Lacteva",
  robots: { index: false, follow: false, nocache: true },
};

export default function BillLayout({ children }: { children: React.ReactNode }) {
  return children;
}
