/**
 * The milk primitives, as contracts (Design System V1.1).
 *
 * The visual half of this system cannot be asserted in a unit test — whether
 * it looks premium is a judgement someone makes with their eyes. What CAN be
 * asserted is the part that would quietly rot: that the liquid never becomes
 * the only carrier of meaning.
 *
 * That is the rule these defend. Every one of these components animates, and
 * every one of them must still work for somebody who cannot see the motion,
 * cannot see the colour, or has asked for neither.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CollectionProgress, MilkFill, MilkStream, MilkVolume } from "@/components/milk";
import { ComingSoonInsight, Insight } from "@/components/insight";
import { Metric, Surface } from "@/components/surface";
import { SyncIndicator } from "@/components/sync-indicator";

describe("the number is always rendered", () => {
  it("MilkVolume states the quantity in text, not only as liquid", () => {
    render(<MilkVolume value={820} max={1000} label="Collected" unit="L" />);
    expect(screen.getByText("820")).toBeInTheDocument();
    expect(screen.getByText("L")).toBeInTheDocument();
  });

  it("CollectionProgress states both the amount and the target", () => {
    render(<CollectionProgress collected={820} target={1000} title="Centre A" />);
    expect(screen.getByText("820")).toBeInTheDocument();
    expect(screen.getByText(/1,000/)).toBeInTheDocument();
    expect(screen.getByText(/82%/)).toBeInTheDocument();
  });
});

describe("assistive technology gets the same information", () => {
  it("MilkFill is a real progressbar with a value and a name", () => {
    render(<MilkFill value={41} max={100} label="Share of target" className="h-10 w-4" />);
    const bar = screen.getByRole("progressbar", { name: "Share of target" });
    expect(bar).toHaveAttribute("aria-valuenow", "41");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps impossible values rather than rendering an impossible bar", () => {
    render(<MilkFill value={9999} max={100} label="Over" />);
    expect(screen.getByRole("progressbar", { name: "Over" })).toHaveAttribute("aria-valuenow", "100");
  });

  it("survives a zero target instead of dividing by it", () => {
    render(<MilkFill value={10} max={0} label="No target" />);
    expect(screen.getByRole("progressbar", { name: "No target" })).toHaveAttribute("aria-valuenow", "0");
  });

  it("MilkStream carries a name for the flow it depicts", () => {
    render(<MilkStream label="Route 1, in progress" />);
    expect(screen.getByRole("img", { name: "Route 1, in progress" })).toBeInTheDocument();
  });

  it("SyncIndicator announces politely and names the state in words", () => {
    render(<SyncIndicator state="syncing" pending={3} />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    // The word, and the count — not a coloured dot.
    expect(region.textContent).toMatch(/Syncing/);
    expect(region.textContent).toMatch(/3 waiting/);
  });
});

describe("intelligence cannot overclaim", () => {
  it("always shows its evidence, without being asked", () => {
    render(
      <Insight
        title="Fat reading is unusual for this farmer"
        basis="4.8% against a 30-day average of 3.9%"
        reasoning="A statistical comparison against that farmer's own trailing average."
      />,
    );
    // The basis is visible immediately — not behind the disclosure.
    expect(screen.getByText(/4.8% against a 30-day average/)).toBeVisible();
  });

  it("keeps the long reasoning collapsed but reachable", async () => {
    render(
      <Insight
        title="Signal"
        basis="Because of X"
        reasoning="The long form an auditor would want."
      />,
    );
    const toggle = screen.getByRole("button", { name: /How this was determined/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/The long form an auditor would want/)).toBeVisible();
  });

  it("says 'coming soon' in words, not by styling alone", () => {
    render(<ComingSoonInsight title="Deeper quality analysis" />);
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });
});

describe("metrics never rely on colour alone", () => {
  it("renders the direction as text beside the tone", () => {
    render(<Metric label="Collected" value="4,206" unit="L" delta={{ direction: "up", text: "3.1% vs yesterday" }} />);
    // Someone who cannot distinguish the green must still read the movement.
    expect(screen.getByText(/3.1% vs yesterday/)).toBeInTheDocument();
  });

  it("uses on-brand foregrounds when it sits on the brand ground", () => {
    // The hero regression: the default supporting colours are tuned for milk
    // and vanish on deep green. A Metric on the brand ground must switch to
    // the measured on-brand tokens, not merely inherit a wrapper colour.
    const { container } = render(
      <Metric onBrand label="Collected today" value="4,206" unit="L" delta={{ direction: "up", text: "3.1%" }} />,
    );
    const html = container.innerHTML;
    expect(html).toContain("text-on-brand-muted");
    expect(html).toContain("text-on-brand-positive");
    expect(html).not.toContain("text-muted-foreground");
    expect(html).not.toContain("text-success");
  });

  it("passes money through as the exact string it was given", () => {
    // The platform's decimals are significant; a metric must not reformat them.
    render(<Metric label="Payable" value="34,440.00" />);
    expect(screen.getByText("34,440.00")).toBeInTheDocument();
  });
});

describe("surfaces", () => {
  it("only lifts when it is actually interactive", () => {
    const { container, rerender } = render(<Surface tone="metric">card</Surface>);
    expect(container.firstElementChild?.className).not.toContain("lacteva-lift");
    rerender(<Surface tone="metric" lift>card</Surface>);
    expect(container.firstElementChild?.className).toContain("lacteva-lift");
  });
});
