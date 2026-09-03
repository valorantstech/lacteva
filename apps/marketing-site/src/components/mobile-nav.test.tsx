import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pathname = vi.fn(() => "/");
vi.mock("next/navigation", () => ({ usePathname: () => pathname() }));

import { SiteHeader } from "@/components/site-header";

/**
 * The site, on a phone (WO-66 · LACTEVA-MARKETING-010).
 *
 * The owner said "there is no place to come back to home page", and two
 * things came out of looking:
 *
 * HOME NOW HAS A WORD. The logo has linked home since the first build and
 * still does — but the person who knows this site best could not find it, so
 * a visitor will not either. A convention only works for people who already
 * know it.
 *
 * THE PHONE MENU. What was here was a horizontally scrolling strip, which did
 * reach every destination — the work order's "unreachable" was drawn from a
 * grep for `hamburger|menu|drawer|sheet|toggle` and a scroll strip is none of
 * those, so nothing became reachable here that was not before. What it did do
 * was spend a row of vertical space on every page at the width where space is
 * scarcest, and hide its own overflow: an item past the right edge had
 * nothing to say it existed, which is what "Home" would have become.
 *
 * These assert the destinations and the behaviour, at the grain a person
 * uses them: open it, press Escape, tab around it.
 */
const DESTINATIONS = [
  ["Home", "/"],
  ["Product", "/product"],
  ["Solutions", "/solutions"],
  ["Pricing", "/pricing"],
  ["About", "/company"],
  ["Login", "/login"],
] as const;

beforeEach(() => pathname.mockReturnValue("/"));

const menuButton = () => screen.getByRole("group").querySelector("summary")!;
const panel = () => screen.getByRole("navigation", { name: /main mobile/i });

describe("the way home", () => {
  it("is a word in the navigation, not only a convention on the logo", () => {
    render(<SiteHeader />);
    const home = screen.getAllByRole("link", { name: /^home$/i });
    expect(home.length).toBeGreaterThan(0);
    for (const link of home) expect(link).toHaveAttribute("href", "/");
  });

  it("is FIRST, because it is where a lost visitor looks", () => {
    render(<SiteHeader />);
    const nav = screen.getByRole("navigation", { name: /^main$/i });
    const labels = within(nav)
      .getAllByRole("link")
      .map((a) => a.textContent?.trim());
    expect(labels[0]).toBe("Home");
  });

  it("keeps the logo linking home, and now says so", () => {
    render(<SiteHeader />);
    const logo = screen.getByRole("link", { name: /lacteva home/i });
    expect(logo).toHaveAttribute("href", "/");
    // The site's own hover affordance. Without it the logo was the only
    // interactive thing in the header that gave no sign of being one.
    expect(logo.className).toContain("lacteva-lift");
    expect(logo.className).toMatch(/hover:/);
  });
});

describe("the phone menu", () => {
  it("reaches every destination, Login included", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);
    await user.click(menuButton());
    for (const [label, href] of DESTINATIONS) {
      expect(
        within(panel()).getByRole("link", { name: new RegExp(`^${label}$`, "i") }),
      ).toHaveAttribute("href", href);
    }
  });

  it("opens and closes from the same control", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);
    const details = screen.getByRole("group") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    await user.click(menuButton());
    expect(details.open).toBe(true);
    await user.click(menuButton());
    expect(details.open).toBe(false);
  });

  it("closes on Escape and gives the keyboard back where it came from", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);
    const details = screen.getByRole("group") as HTMLDetailsElement;
    await user.click(menuButton());
    expect(details.open).toBe(true);
    await user.keyboard("{Escape}");
    expect(details.open).toBe(false);
    // A menu that closes and strands focus on the body leaves a keyboard
    // visitor with no idea where they are.
    expect(document.activeElement).toBe(menuButton());
  });

  it("puts the keyboard on the first destination when it opens", async () => {
    const user = userEvent.setup();
    render(<SiteHeader />);
    await user.click(menuButton());
    expect(document.activeElement).toBe(
      within(panel()).getByRole("link", { name: /^home$/i }),
    );
  });

  it("keeps the keyboard inside while it is open", async () => {
    // While the menu covers the navigation, tabbing behind it lands on
    // content the visitor cannot see.
    const user = userEvent.setup();
    render(<SiteHeader />);
    await user.click(menuButton());
    const links = within(panel()).getAllByRole("link");
    links[links.length - 1].focus();
    await user.tab();
    expect(document.activeElement).toBe(links[0]);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(links[links.length - 1]);
  });

  it("closes when the route changes, rather than covering the new page", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<SiteHeader />);
    await user.click(menuButton());
    expect((screen.getByRole("group") as HTMLDetailsElement).open).toBe(true);
    // Tapping a destination navigates; the pathname is what changes.
    pathname.mockReturnValue("/pricing");
    rerender(<SiteHeader />);
    expect((screen.getByRole("group") as HTMLDetailsElement).open).toBe(false);
  });

  it("works with no JavaScript, which is what `details` buys", () => {
    // The header promises the site is navigable without a bundle. A menu
    // built on a div and a click handler would have quietly ended that for
    // every phone visitor — the audience this product is sold to.
    render(<SiteHeader />);
    const details = screen.getByRole("group");
    expect(details.tagName).toBe("DETAILS");
    expect(details.querySelector("summary")).not.toBeNull();
  });

  it("names itself for a screen reader", () => {
    render(<SiteHeader />);
    expect(menuButton()).toHaveAttribute("aria-label", "Menu");
  });
});
