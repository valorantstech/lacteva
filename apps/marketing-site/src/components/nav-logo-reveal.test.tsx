import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NavLogoReveal } from "./nav-logo-reveal";

/**
 * The nav logo reveal (LACTEVA-MARKETING-002): plays the LogoReveal board's
 * three beats exactly once per visit — sessionStorage-gated — and never for
 * a reader who asked their OS for less motion.
 */
describe("NavLogoReveal", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const revealState = (container: HTMLElement) =>
    container.querySelector("[data-reveal]")?.getAttribute("data-reveal");

  it("plays the three beats on the first visit and records having done so", () => {
    const { container } = render(<NavLogoReveal />);
    expect(revealState(container)).toBe("on");
    // The beats are all present for the CSS to choreograph.
    expect(container.querySelector(".nav-reveal-drop")).toBeInTheDocument();
    expect(container.querySelectorAll("[data-reveal-ring]")).toHaveLength(2);
    expect(container.querySelector(".nav-reveal-word")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("lacteva-nav-reveal")).toBe("1");
  });

  it("stays static for the rest of the session", () => {
    render(<NavLogoReveal />);
    const { container } = render(<NavLogoReveal />);
    expect(revealState(container)).toBe("off");
    // The lockup itself is still there.
    expect(container.textContent).toContain("Lacteva");
  });

  it("never plays under prefers-reduced-motion", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: true }),
    );
    const { container } = render(<NavLogoReveal />);
    expect(revealState(container)).toBe("off");
    // The gate is not spent either — motion was refused, not consumed.
    expect(window.sessionStorage.getItem("lacteva-nav-reveal")).toBeNull();
  });

  it("renders the static lockup when storage is unavailable", () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    const { container } = render(<NavLogoReveal />);
    expect(revealState(container)).toBe("off");
    expect(container.textContent).toContain("Lacteva");
  });
});
