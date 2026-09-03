"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";

export type NavItem = { readonly href: string; readonly label: string };

/**
 * The site's navigation, on a phone (WO-66 · LACTEVA-MARKETING-010).
 *
 * WHAT WAS HERE BEFORE, and what was actually wrong with it. The header
 * carried a second `<nav>` below the md breakpoint: a horizontally scrolling
 * strip of the same links. So the destinations WERE reachable on a phone —
 * the work order's "unreachable" was drawn from a grep for
 * `hamburger|menu|drawer|sheet|toggle`, which finds nothing because a scroll
 * strip is none of those. What was wrong is subtler and still worth fixing:
 * a strip costs a row of vertical space on every page at the width where
 * space is scarcest, and it hides its own overflow — a fifth item sits off
 * the right edge with nothing to say it is there, which is exactly what
 * adding "Home" would have done.
 *
 * SO THIS IS A DISCLOSURE, NOT A MODAL, and the distinction decides the
 * behaviour. It does not cover the page or make the rest of it inert, so it
 * does not claim `aria-modal`. It is built on `<details>`/`<summary>`, which
 * means:
 *
 *   IT WORKS WITH NO JAVASCRIPT. The header's own docstring promises the site
 *   is navigable without it, and a menu that needed a bundle to open would
 *   have quietly ended that. The markup ships in the HTML; everything below
 *   is enhancement.
 *
 *   THE KEYBOARD WORKS BY DEFAULT. `<summary>` is focusable and toggles on
 *   Enter and Space without a line of code, and the browser announces
 *   expanded and collapsed. Rebuilding that on a `<div>` is how a menu ends
 *   up unreachable for the people who most need it to work.
 *
 * Motion is a CSS transition, so the site's global
 * `prefers-reduced-motion` rule collapses it to 0.01ms without this file
 * knowing the rule exists.
 */
export function MobileNav({ items }: { items: readonly NavItem[] }) {
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  // OPEN IS DERIVED FROM THE ROUTE, not synchronised to it.
  //
  // The menu is open for the page it was opened on, so navigating closes it
  // by arithmetic rather than by an effect — tapping a destination must not
  // leave the menu sitting over the page the visitor just asked for. Written
  // as an effect this would be a `setState` inside `useEffect`, which
  // cascades a second render and which React (and this project's lint rule)
  // asks you not to do: the state React already has is enough.
  const [openFor, setOpenFor] = useState<string | null>(null);
  const open = openFor === pathname;
  // `close` rather than a `setOpen(boolean)`: every caller below closes, and
  // `setOpenFor(null)` is a stable setter, so the effect's dependency list
  // stays honest — a helper redefined each render would either lie in the
  // list or be excluded from it.
  const close = () => setOpenFor(null);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        // Focus goes back where it came from. A menu that closes and leaves
        // focus on the document body strands a keyboard visitor at the top
        // of the page with no idea where they are.
        summary.current?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      // Keep the keyboard inside the open menu. This is the one modal-ish
      // behaviour a disclosure earns: while it is open it covers the
      // navigation, and tabbing behind it lands on content the visitor
      // cannot see.
      const focusable = panel.current?.querySelectorAll<HTMLElement>("a[href]");
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === summary.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    // A tap anywhere else closes it, which is what every visitor expects and
    // what makes the menu feel like a menu rather than a page.
    const onPointerDown = (event: PointerEvent) => {
      if (!details.current?.contains(event.target as Node)) close();
    };

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    // Focus the first destination, so opening the menu and pressing Enter
    // goes somewhere rather than nowhere.
    panel.current?.querySelector<HTMLElement>("a[href]")?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  return (
    <details
      ref={details}
      open={open}
      className="relative md:hidden"
      onToggle={(event) =>
        setOpenFor((event.currentTarget as HTMLDetailsElement).open ? pathname : null)
      }
    >
      <summary
        ref={summary as React.RefObject<HTMLElement>}
        aria-label="Menu"
        className="lacteva-lift flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-lg border border-border/70 text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden"
      >
        {/* Two icons, one rendered: the bars become a cross when open, which
            is the only affordance saying the same control closes it. */}
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="size-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          {open ? (
            <path d="M6 6l12 12M18 6L6 18" />
          ) : (
            <path d="M4 7h16M4 12h16M4 17h16" />
          )}
        </svg>
      </summary>
      <div
        ref={panel}
        className="absolute end-0 top-12 z-50 w-56 rounded-xl border border-border/70 bg-background p-2 shadow-lg"
      >
        <nav aria-label="Main mobile" className="flex flex-col">
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
          {/* Login belongs in here for the same reason it is in the desktop
              header: an existing customer arriving on a phone is not a
              visitor to be sold to, and they were the person the broken
              /login page turned away (WO-65). */}
          <Link
            href="/login"
            prefetch={false}
            className="rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Login
          </Link>
        </nav>
      </div>
    </details>
  );
}
