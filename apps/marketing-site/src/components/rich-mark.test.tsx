import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RichDrop } from "./logo";
import { NavLogoReveal } from "./nav-logo-reveal";
import { SiteFooter } from "./site-footer";

/**
 * The rich mark's rendering contract (LACTEVA-MARKETING-003). The numbers
 * themselves are pinned by brand-mark.test.ts and check_inline.py; what
 * these cases pin is the part only a render can prove: the lit drop is
 * actually on the surfaces that adopted it, and two instances on one page
 * do not fight over SVG ids (ids are document-global — a collision makes
 * one drop silently borrow the other's gradients).
 */
describe("the rich mark on the site", () => {
  it("two instances keep their gradient defs apart", () => {
    const { container } = render(
      <>
        <RichDrop idPrefix="a" />
        <RichDrop idPrefix="b" />
      </>,
    );
    const gradients = container.querySelectorAll("linearGradient");
    expect(gradients).toHaveLength(2);
    const ids = [...gradients].map((node) => node.id);
    expect(new Set(ids).size).toBe(2);
    // Each drop's body fill points at its own def, not its sibling's.
    for (const svg of container.querySelectorAll("svg")) {
      const id = svg.querySelector("linearGradient")?.id;
      expect(
        svg.querySelector('path[fill^="url("]')?.getAttribute("fill"),
      ).toBe(`url(#${id})`);
    }
  });

  it("the nav reveal plays with the lit drop", () => {
    const { container } = render(<NavLogoReveal />);
    // The animated element carries the rich rendering: gradient body,
    // highlight ellipse, meniscus — not a flat fill.
    const drop = container.querySelector(".nav-reveal-drop");
    expect(drop).not.toBeNull();
    expect(drop!.querySelector("ellipse")).not.toBeNull();
    expect(drop!.querySelector("linearGradient")).not.toBeNull();
  });

  it("the footer lockup is the rich drop on the ink band", () => {
    const { container } = render(<SiteFooter />);
    expect(container.querySelector("ellipse")).not.toBeNull();
    expect(container.textContent).toContain("Lacteva");
  });
});
