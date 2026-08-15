import Link from "next/link";
import { Wordmark } from "@/components/logo";

const COLUMNS = [
  {
    heading: "Product",
    links: [
      { href: "/product", label: "How Lacteva works" },
      { href: "/editions", label: "Editions" },
      { href: "/why-lacteva", label: "Why Lacteva" },
    ],
  },
  {
    heading: "Company",
    links: [
      { href: "/company", label: "About Phoenix Software" },
      { href: "/request-demo", label: "Request a demo" },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-secondary/40">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-10 sm:flex-row">
          <div className="flex max-w-sm flex-col gap-3">
            <Wordmark />
            <p className="text-sm leading-relaxed text-muted-foreground">
              The dairy platform for organizations that buy milk from many
              small producers and turn it into money that must be trusted on
              both sides of the scale.
            </p>
          </div>
          <div className="flex gap-16">
            {COLUMNS.map((col) => (
              <div key={col.heading} className="flex flex-col gap-3">
                <p className="text-xs font-semibold tracking-wide text-foreground uppercase">
                  {col.heading}
                </p>
                {col.links.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2 border-t border-border/70 pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>Lacteva is the flagship product of Phoenix Software.</p>
          <p>&copy; {new Date().getFullYear()} Phoenix Software</p>
        </div>
      </div>
    </footer>
  );
}
