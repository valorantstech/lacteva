import Link from "next/link";
import { LinkButton } from "@/components/link-button";
import { MobileNav } from "@/components/mobile-nav";
import { NavLogoReveal } from "@/components/nav-logo-reveal";

// Final navigation (MKT-004E). "Resources" stays deferred until there is
// real content to put behind it. "About" → /company is intentional.
//
// WO-66: HOME IS FIRST, and it is here because the owner of this product
// could not find the way back to it. The logo has linked home since the
// first build and still does — but a convention only works for people who
// know it, and "everyone knows the logo goes home" is an assumption that had
// already failed for the person who knows this site best. A word costs one
// nav slot and assumes nothing.
const NAV = [
  { href: "/", label: "Home" },
  { href: "/product", label: "Product" },
  { href: "/solutions", label: "Solutions" },
  { href: "/pricing", label: "Pricing" },
  { href: "/company", label: "About" },
] as const;

/**
 * Server component; the whole site is navigable without JavaScript — the
 * phone menu is a `<details>` element, so that stays true below the md
 * breakpoint too. Login goes through /login, which hands over to the
 * separately deployed authenticated portal — the two applications share a
 * link, never a UI.
 * The one client leaf is the logo lockup, whose reveal plays on a
 * visitor's first page (LACTEVA-MARKETING-002) and renders statically
 * everywhere else.
 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/90 backdrop-blur">
      {/* WO-97: below `sm` the row is logo + Menu and nothing else — the CTA
          moves into the menu (it is the hero's first button anyway). Logo,
          "Start Free Trial" and the Menu did not fit a 360px phone: the Menu
          button, the only way to navigate on a phone, ended 7px off the edge
          and the whole site zoomed out. Measured on live, D-45. */}
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-3 px-4 sm:gap-6 sm:px-6 lg:px-8">
        {/* WO-66: the logo keeps its link home AND now says it is one.
            `lacteva-lift` is the site's own hover affordance, used by every
            other link in this header; without it the logo was the only
            interactive thing on the page that gave no sign of being one. */}
        <Link
          href="/"
          aria-label="Lacteva home"
          className="lacteva-lift shrink-0 rounded-lg transition-opacity hover:opacity-80"
        >
          <NavLogoReveal />
        </Link>
        <nav aria-label="Main" className="hidden items-center gap-6 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="lacteva-lift text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/login"
            prefetch={false}
            className="lacteva-lift hidden text-sm font-medium text-muted-foreground transition-colors hover:text-foreground sm:block"
          >
            Login
          </Link>
          <span className="hidden sm:block">
            <LinkButton href="/start-free-trial" size="lg">
              Start Free Trial
            </LinkButton>
          </span>
          {/* WO-66: the phone's way into the site. It REPLACES the scrolling
              strip that used to sit under this bar — that strip did reach
              every destination, so nothing became reachable that was not
              before, but it spent a row of vertical space on every page at
              the width where space is scarcest and hid its own overflow: a
              fifth item sat off the right edge with nothing to say so, which
              is precisely what adding "Home" would have done to it. */}
          <MobileNav items={NAV} />
        </div>
      </div>
    </header>
  );
}
