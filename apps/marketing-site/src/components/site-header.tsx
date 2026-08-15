import Link from "next/link";
import { LinkButton } from "@/components/link-button";
import { Wordmark } from "@/components/logo";

// Grows toward Product / Solutions / Pricing / About as those pages land
// (MKT-004D/E). Only routes that exist are listed — no dead links.
const NAV = [
  { href: "/product", label: "Product" },
  { href: "/solutions", label: "Solutions" },
  { href: "/why-lacteva", label: "Why Lacteva" },
  { href: "/company", label: "About" },
] as const;

/**
 * Server component; the whole site is navigable without JavaScript. The
 * "Sign in" link points at the separate authenticated admin portal and only
 * renders when a portal URL is configured — the two applications share a
 * link, never a UI.
 */
export function SiteHeader() {
  const portalUrl = process.env.NEXT_PUBLIC_PORTAL_URL;
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-6 px-4 sm:px-6 lg:px-8">
        <Link href="/" aria-label="Lacteva home" className="shrink-0">
          <Wordmark />
        </Link>
        <nav aria-label="Main" className="hidden items-center gap-6 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {portalUrl ? (
            <a
              href={portalUrl}
              className="hidden text-sm font-medium text-muted-foreground transition-colors hover:text-foreground sm:block"
            >
              Login
            </a>
          ) : null}
          <LinkButton href="/request-demo" size="lg">
            Request a demo
          </LinkButton>
        </div>
      </div>
      <nav
        aria-label="Main mobile"
        className="flex items-center gap-5 overflow-x-auto border-t border-border/60 px-4 py-2 md:hidden"
      >
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="text-sm font-medium whitespace-nowrap text-muted-foreground"
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
