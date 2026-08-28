import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CtaBand } from "./cta-band";
import { CAN_PATH, MARK_PATH, TAGLINE, Wordmark } from "./logo";
import { NavLogoReveal } from "./nav-logo-reveal";
import { SiteFooter } from "./site-footer";

/**
 * The lockup's rendering contract (LACTEVA-MARKETING-003 · -007). The
 * numbers themselves are pinned by brand-mark.test.ts and check_inline.py;
 * what these cases pin is the part only a render can prove: the final
 * lockup is actually on the surfaces that adopted it, the on-ink variant is
 * the one the dark band gets, and two instances on one page do not fight
 * over SVG ids (ids are document-global — a collision makes one lockup
 * silently borrow the other's gradients).
 */
describe("the lockup on the site", () => {
  it("two instances keep their gradient defs apart", () => {
    const { container } = render(
      <>
        <Wordmark idPrefix="a" />
        <Wordmark idPrefix="b" />
      </>,
    );
    const gradients = container.querySelectorAll("linearGradient");
    expect(gradients).toHaveLength(2);
    const ids = [...gradients].map((node) => node.id);
    expect(new Set(ids).size).toBe(2);
    // Each VA fill points at its own def, not its sibling's.
    for (const svg of container.querySelectorAll("svg")) {
      const id = svg.querySelector("linearGradient")?.id;
      expect(
        svg.querySelector('path[fill^="url("]')?.getAttribute("fill"),
      ).toBe(`url(#${id})`);
    }
  });

  it("the nav reveal drops the lit drop into the can", () => {
    const { container } = render(<NavLogoReveal />);
    // The animated element carries the rich rendering: gradient body,
    // highlight ellipse, meniscus — not a flat fill.
    const drop = container.querySelector(".nav-reveal-drop");
    expect(drop).not.toBeNull();
    expect(drop!.querySelector("ellipse")).not.toBeNull();
    expect(drop!.querySelector("linearGradient")).not.toBeNull();
    // And it falls into the FINAL lockup: the can behind it, the traced
    // letterforms as beat 3 — not a word set in the UI font.
    const svg = container.querySelector("svg")!;
    expect(svg.querySelector(`path[d="${CAN_PATH}"]`)).not.toBeNull();
    const word = svg.querySelector(".nav-reveal-word");
    expect(word).not.toBeNull();
    expect(word!.querySelectorAll("path")).toHaveLength(2);
    expect(container.textContent).toContain("Lacteva");
  });

  it("the footer wears the on-ink lockup, and the tagline", () => {
    const { container } = render(<SiteFooter />);
    const can = container.querySelector(`path[d="${CAN_PATH}"]`);
    const drop = container.querySelector(`path[d="${MARK_PATH}"]`);
    // The generated on-ink variant: cream can body, deep drop — and no
    // gradient, because the VA run would vanish on the dark band.
    expect(can?.getAttribute("fill")).toBe("#FDFBF4");
    expect(drop?.getAttribute("fill")).toBe("#0E3D14");
    expect(container.querySelector("linearGradient")).toBeNull();
    expect(container.textContent).toContain("Lacteva");
    expect(container.textContent).toContain(TAGLINE);
  });

  it("the CTA band carries the tagline — its only home besides the footer", () => {
    const { container } = render(<CtaBand />);
    expect(container.textContent).toContain(TAGLINE);
  });
});
