import Link from "next/link";
import { Wordmark } from "@/components/logo";

const COLUMNS = [
  {
    heading: "Product",
    links: [
      { href: "/product", label: "How Lacteva works" },
      { href: "/solutions", label: "Solutions" },
      { href: "/pricing", label: "Pricing" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/company", label: "About Phoenix Software" },
      { href: "/start-free-trial", label: "Start Free Trial" },
      { href: "/request-demo", label: "Book a Demo" },
      { href: "/login", label: "Login" },
    ],
  },
] as const;

/**
 * The footer is the site's one standing ink band: it closes every page on
 * the dark surface, which is what lets content sections stay light.
 */
export function SiteFooter() {
  return (
    <footer className="bg-ink text-ink-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-10 sm:flex-row">
          <div className="flex max-w-sm flex-col gap-3">
            <Wordmark className="text-ink-foreground" />
            <p className="text-sm leading-relaxed text-ink-muted">
              One connected platform for modern dairy operations — from milk
              procurement through delivery, billing, payments, and reporting.
            </p>
          </div>
          <div className="flex gap-16">
            {COLUMNS.map((col) => (
              <div key={col.heading} className="flex flex-col gap-3">
                <p className="text-xs font-semibold tracking-wide text-ink-foreground uppercase">
                  {col.heading}
                </p>
                {col.links.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    prefetch={link.href === "/login" ? false : undefined}
                    className="text-sm text-ink-muted transition-colors hover:text-ink-foreground"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 border-t border-ink-foreground/10 pt-6 text-xs text-ink-muted sm:flex-row sm:items-center sm:justify-between">
          <p>Lacteva is the flagship product of Phoenix Software.</p>
          <p>&copy; {new Date().getFullYear()} Phoenix Software</p>
        </div>
      </div>
    </footer>
  );
}
