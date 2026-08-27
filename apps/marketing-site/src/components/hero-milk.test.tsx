import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HeroMilk } from "./hero-milk";

/**
 * The living hero's contract is its fallback: the approved board's static
 * composition is the server render, and the canvas fluid only takes over
 * after a 2D context exists and the simulation starts. jsdom has no canvas
 * implementation, which makes it exactly the "weak device" the work order
 * requires to degrade gracefully — the component must land on the static
 * composition without throwing.
 */
describe("HeroMilk", () => {
  it("serves the static composition when no canvas context exists", () => {
    const { container } = render(<HeroMilk />);
    const figure = container.firstElementChild;
    // data-motion never reaches "live" — the crossfade CSS keys off it.
    expect(figure).toHaveAttribute("data-motion", "static");
    // The board's composition: pour stream + milk body are in the render.
    expect(container.querySelector("[data-hero-static]")).toBeInTheDocument();
    expect(container.querySelector(".hero-pour")).toBeInTheDocument();
  });

  it("is decorative — hidden from assistive tech entirely", () => {
    const { container } = render(<HeroMilk />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });
});
