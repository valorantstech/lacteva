import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScrollMotion } from "./scroll-motion";

/**
 * The scroll settle-ins (LACTEVA-MARKETING-004). What matters is the
 * failure order: the page is visible FIRST and animated second — so a
 * missing IntersectionObserver, reduced motion, or a section already on
 * screen must all leave the DOM untouched, and only a below-the-fold
 * section may ever be armed (hidden) and then released (settle-go).
 */

function mountSections() {
  document.body.innerHTML = `
    <section data-settle id="above"><div><h2>seen</h2><p>copy</p></div></section>
    <section data-settle id="below"><div><h2>later</h2><p>copy</p><div>grid</div></div></section>
  `;
  const above = document.getElementById("above")!;
  const below = document.getElementById("below")!;
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
  above.getBoundingClientRect = () => ({ top: 200 }) as DOMRect;
  below.getBoundingClientRect = () => ({ top: 1200 }) as DOMRect;
  return { above, below };
}

describe("ScrollMotion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("arms only sections below the fold, staggers their children, and releases on entry", () => {
    const { above, below } = mountSections();
    const observed: Element[] = [];
    let callback: (entries: Array<{ target: Element; isIntersecting: boolean }>) => void = () => {};
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: typeof callback) {
          callback = cb;
        }
        observe(el: Element) {
          observed.push(el);
        }
        unobserve() {}
        disconnect() {}
      },
    );
    render(<ScrollMotion />);

    // A section already on screen is never touched — nothing blinks.
    expect(above.classList.contains("settle-armed")).toBe(false);
    // The below-fold section is armed and its children staggered ≤40ms.
    expect(below.classList.contains("settle-armed")).toBe(true);
    expect(observed).toEqual([below]);
    const children = below.querySelectorAll(":scope > div > *");
    expect((children[0] as HTMLElement).style.getPropertyValue("--settle-delay")).toBe("0ms");
    expect((children[1] as HTMLElement).style.getPropertyValue("--settle-delay")).toBe("40ms");
    expect((children[2] as HTMLElement).style.getPropertyValue("--settle-delay")).toBe("80ms");

    // Entering the viewport releases it, once.
    callback([{ target: below, isIntersecting: true }]);
    expect(below.classList.contains("settle-go")).toBe(true);
  });

  it("does nothing at all without IntersectionObserver — the page stays visible", () => {
    const { above, below } = mountSections();
    // jsdom has no IntersectionObserver; the component must simply no-op.
    render(<ScrollMotion />);
    expect(above.classList.contains("settle-armed")).toBe(false);
    expect(below.classList.contains("settle-armed")).toBe(false);
  });

  it("never arms under prefers-reduced-motion", () => {
    const { below } = mountSections();
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    render(<ScrollMotion />);
    expect(below.classList.contains("settle-armed")).toBe(false);
  });

  it("drifts a [data-parallax] element with a clamped, transform-only offset", () => {
    // The parallax (LACTEVA-MARKETING-008): a scene far from the viewport
    // centre gets its counter-drift immediately — transform only, and
    // never more than 14px however far away it is.
    mountSections();
    const scene = document.createElement("div");
    scene.setAttribute("data-parallax", "0.05");
    scene.getBoundingClientRect = () =>
      ({ top: 1000, height: 200 }) as DOMRect;
    document.body.appendChild(scene);
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    render(<ScrollMotion />);
    // centre 1100 vs viewport middle 400 → raw −35px, clamped to −14.
    expect(scene.style.transform).toBe("translateY(-14px)");
  });

  it("never drifts under prefers-reduced-motion — the scene just sits", () => {
    mountSections();
    const scene = document.createElement("div");
    scene.setAttribute("data-parallax", "0.05");
    scene.getBoundingClientRect = () =>
      ({ top: 1000, height: 200 }) as DOMRect;
    document.body.appendChild(scene);
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    render(<ScrollMotion />);
    expect(scene.style.transform).toBe("");
  });
});
