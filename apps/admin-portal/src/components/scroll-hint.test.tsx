/**
 * A wide table says it scrolls (WO-96 §3): a fade on the edge that has more.
 */
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScrollHint } from "@/components/scroll-hint";

function sized(el: HTMLElement, { scrollWidth, clientWidth }: { scrollWidth: number; clientWidth: number }) {
  Object.defineProperty(el, "scrollWidth", { configurable: true, get: () => scrollWidth });
  Object.defineProperty(el, "clientWidth", { configurable: true, get: () => clientWidth });
}

describe("ScrollHint", () => {
  it("shows the right-edge cue when there is more to the right, and drops it once scrolled there", async () => {
    render(
      <ScrollHint data-testid="scroller">
        <table>
          <tbody>
            <tr>
              <td>wide</td>
            </tr>
          </tbody>
        </table>
      </ScrollHint>,
    );
    const scroller = screen.getByTestId("scroller");
    sized(scroller, { scrollWidth: 1400, clientWidth: 360 });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
    expect(screen.getByTestId("scroll-hint-right")).toBeInTheDocument();
    expect(screen.queryByTestId("scroll-hint-left")).toBeNull();

    // Scrolled to the far right: only the left cue remains.
    scroller.scrollLeft = 1040;
    await act(async () => {
      scroller.dispatchEvent(new Event("scroll"));
    });
    expect(screen.queryByTestId("scroll-hint-right")).toBeNull();
    expect(screen.getByTestId("scroll-hint-left")).toBeInTheDocument();
  });

  it("shows nothing when the content fits", async () => {
    render(
      <ScrollHint data-testid="scroller">
        <span>narrow</span>
      </ScrollHint>,
    );
    sized(screen.getByTestId("scroller"), { scrollWidth: 300, clientWidth: 360 });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
    expect(screen.queryByTestId("scroll-hint-right")).toBeNull();
    expect(screen.queryByTestId("scroll-hint-left")).toBeNull();
  });
});
