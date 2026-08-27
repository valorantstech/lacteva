/**
 * The reveal, and the promise it must not break (LACTEVA-BRAND-003).
 *
 * A brand animation over a sign-in page is the easiest place in a product to
 * do harm: it is the first thing a person meets and the last thing they want
 * when they came to type a password. So most of what is pinned here is what
 * it must NOT do — stand in front of the form, play twice a session, or run
 * for somebody who asked for no animation.
 *
 * The mark itself is checked by `brand-mark.test.ts` against
 * `tools/brand/mark.json`; this file is about the behaviour around it.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginReveal, REVEAL_MS, shouldReveal } from "@/components/login-reveal";
import { BrandMark } from "@/components/brand-mark";

/** A `matchMedia` that answers a single question honestly. */
function stubMotion(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query.includes("prefers-reduced-motion") ? reduced : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    })),
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  stubMotion(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the gate", () => {
  it("plays once a session and not twice", () => {
    const store = new Map<string, string>();
    const fake = { getItem: (k: string) => store.get(k) ?? null };
    expect(shouldReveal(fake, false)).toBe(true);
    store.set("lacteva.reveal.played", "1");
    expect(shouldReveal(fake, false)).toBe(false);
  });

  it("never plays under reduced motion, whatever the store says", () => {
    // Checked FIRST, so a person who will not see it does not have the
    // session spent on their behalf either.
    expect(shouldReveal(null, true)).toBe(false);
    expect(
      shouldReveal({ getItem: () => null }, true),
      "an empty store must not override the preference",
    ).toBe(false);
  });

  it("a browser that refuses storage still gets a working page", () => {
    // Private mode, blocked site data. Playing every time beats throwing.
    const hostile = {
      getItem: () => {
        throw new DOMException("denied");
      },
    };
    expect(shouldReveal(hostile, false)).toBe(true);
  });
});

describe("the reveal", () => {
  it("plays on the first visit of the session, then removes itself", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<LoginReveal />);
    await waitFor(() =>
      expect(screen.getByTestId("login-reveal")).toBeTruthy(),
    );

    // The three beats, and then gone. 1.4s is the board's total.
    expect(REVEAL_MS).toBe(1400);
    vi.advanceTimersByTime(REVEAL_MS + 20);
    await waitFor(() =>
      expect(screen.queryByTestId("login-reveal")).toBeNull(),
    );
  });

  it("does not play again in the same session", async () => {
    const { unmount } = render(<LoginReveal />);
    await waitFor(() =>
      expect(screen.getByTestId("login-reveal")).toBeTruthy(),
    );
    unmount();

    render(<LoginReveal />);
    // A second visit within the session gets the page, not the entrance.
    await waitFor(() =>
      expect(screen.queryByTestId("login-reveal")).toBeNull(),
    );
  });

  it("renders nothing at all under reduced motion", async () => {
    stubMotion(true);
    render(<LoginReveal />);
    await waitFor(() =>
      expect(screen.queryByTestId("login-reveal")).toBeNull(),
    );
    // And the session was NOT spent: turning the preference off later still
    // earns a welcome.
    expect(window.sessionStorage.getItem("lacteva.reveal.played")).toBeNull();
  });

  it("never stands in front of the form", async () => {
    // The overlay is decoration over a working page. It intercepts no pointer
    // at all, so a click aimed at the email field reaches the email field.
    render(<LoginReveal />);
    const overlay = await screen.findByTestId("login-reveal");
    expect(overlay.className).toContain("pointer-events-none");
    // And it is hidden from assistive technology, which has no use for an
    // entrance it cannot see.
    expect(overlay.getAttribute("aria-hidden")).toBe("true");
  });

  it("a pointer anywhere ends it early", async () => {
    render(<LoginReveal />);
    await waitFor(() =>
      expect(screen.getByTestId("login-reveal")).toBeTruthy(),
    );
    window.dispatchEvent(new Event("pointerdown"));
    await waitFor(() =>
      expect(screen.queryByTestId("login-reveal")).toBeNull(),
    );
  });
});

describe("the rich mark", () => {
  it("is drawn, and drawn for the eye rather than the screen reader", () => {
    const { container } = render(<BrandMark size={64} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    // The three things that make it rich, and no more.
    expect(container.querySelector("linearGradient")).toBeTruthy();
    expect(container.querySelector("radialGradient")).toBeTruthy();
    expect(container.querySelector("ellipse")).toBeTruthy();
    expect(container.querySelector("clipPath")).toBeTruthy();
  });

  it("is taller than it is wide — a drop, not a disc", () => {
    const { container } = render(<BrandMark size={100} />);
    const svg = container.querySelector("svg")!;
    expect(Number(svg.getAttribute("height"))).toBeGreaterThan(
      Number(svg.getAttribute("width")),
    );
  });
});
