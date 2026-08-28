/**
 * The front door wears the brand (WO-39).
 *
 * The owner looked at the LIVE portal and was right: the shell had worn the
 * final identity since WO-31, but `/login` still showed BRAND-003's lit drop
 * with "Lacteva" set in the UI font — two brand generations behind the frame
 * around it, and the first thing a customer sees at the real URL.
 *
 * What is pinned here is not a look. It is the two things that made the drift
 * possible and would let it happen again:
 *
 *   1. every auth page draws the ONE generated composition, so a fourth page
 *      cannot arrive with a fifth arrangement of the same parts;
 *   2. neither retired rendering can come back — not the lit drop, and not
 *      the wordmark set in a typeface, which BRAND-004 Amendment 1 forbids on
 *      any committed surface.
 *
 * The path data itself is guarded by `tools/brand/check_inline.py`, which
 * regenerates it and compares. This file guards the SURFACES.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import LoginPage from "@/app/login/page";
import ResetPasswordPage from "@/app/reset-password/page";
import AcceptInvitationPage from "@/app/accept-invitation/page";
import { LactevaLockup, WORDMARK_TAGLINE_PATH } from "@/components/lockup";

const PAGES = [
  ["/login", LoginPage],
  ["/reset-password", ResetPasswordPage],
  ["/accept-invitation", AcceptInvitationPage],
] as const;

describe("every auth page carries the lockup", () => {
  it.each(PAGES)("%s draws the can, the letterforms and the tagline", (_label, Page) => {
    const { container } = render(<Page />);
    // Two drawings: the can, and the traced artwork.
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThanOrEqual(2);
    // The tagline is the layer only the full lockup carries — its presence
    // is what separates "the lockup" from "a mark someone put at the top".
    expect(container.innerHTML).toContain(WORDMARK_TAGLINE_PATH.slice(0, 60));
  });

  it.each(PAGES)("%s arrives on the DS settle token", (_label, Page) => {
    const { container } = render(<Page />);
    // `lacteva-settle` is the Design System's "something arrived" animation,
    // and globals.css collapses every animation to 1ms under
    // prefers-reduced-motion — so this one class is also the guarantee that
    // reduced motion gets the finished page instantly and complete.
    expect(container.querySelectorAll(".lacteva-settle").length).toBeGreaterThan(0);
  });

  it.each(PAGES)("%s sits on the dairy wash, from a DS token", (_label, Page) => {
    const { container } = render(<Page />);
    // The token, not a colour invented here.
    expect(container.innerHTML).toContain("--gradient-cream-fresh");
  });
});

describe("the lockup is one composition, not per-page markup", () => {
  it("renders the same drawing wherever it is used", () => {
    const { container: alone } = render(<LactevaLockup withTagline idPrefix="login" />);
    const { container: page } = render(<LoginPage />);
    // Every path the component draws appears on the page, byte for byte.
    for (const path of Array.from(alone.querySelectorAll("path"))) {
      expect(page.innerHTML).toContain(path.getAttribute("d"));
    }
  });

  it("gives each instance its own gradient id", () => {
    // SVG ids are document-global. Two lockups on one document sharing an id
    // is a gradient that silently resolves to whichever mounted last.
    const { container } = render(
      <>
        <LactevaLockup withTagline idPrefix="a" />
        <LactevaLockup withTagline idPrefix="b" />
      </>,
    );
    const ids = Array.from(container.querySelectorAll("linearGradient")).map((g) =>
      g.getAttribute("id"),
    );
    expect(new Set(ids).size).toBe(ids.length);
  });
});

/** Every page and component file under src. */
function sources(dir = "src"): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx$/.test(entry.name) && !/\.test\.tsx$/.test(entry.name)
      ? [path]
      : [];
  });
}

describe("the retired renderings cannot come back", () => {
  const AUTH = [
    join("src", "app", "login", "page.tsx"),
    join("src", "app", "reset-password", "page.tsx"),
    join("src", "app", "accept-invitation", "page.tsx"),
  ];

  it.each(PAGES)("%s does not set the product's name in a typeface", (_label, Page) => {
    // BRAND-004 Amendment 1: no committed surface may carry a font-rendered
    // approximation of LACTEVA. The login page carried exactly that —
    // `<span className="text-xl font-semibold">Lacteva</span>` above the
    // card — for two brand generations.
    //
    // Asserted on what RENDERS, not on the source. A source scan cannot tell
    // the name apart from the `LactevaLockup` identifier that draws it, or
    // from a comment explaining why the text is gone, and a guard that
    // cannot make that distinction is one somebody silences.
    render(<Page />);
    expect(screen.queryByText("Lacteva")).toBeNull();
    expect(screen.queryByText(/^Lacteva$/)).toBeNull();
  });

  it("the retired lit-drop reveal is gone, and nothing imports it", () => {
    // WO-20's once-a-session reveal drew BRAND-003's lit drop, which stopped
    // being the mark when BRAND-004 made the can the outer shape. Mobile
    // retired its equivalent in WO-33; this is the portal's.
    for (const file of sources()) {
      const source = readFileSync(file, "utf8");
      expect(source, `${file} imports the retired reveal`).not.toContain(
        "login-reveal",
      );
    }
  });

  it("no auth page draws the lit drop", () => {
    for (const file of AUTH) {
      const source = readFileSync(file, "utf8");
      expect(source, `${file} still uses BrandMark`).not.toMatch(
        /\bBrandMark\b/,
      );
    }
  });
});
