/**
 * The dairy, at a glance (LACTEVA-ADMIN-015; board: Dashboard).
 *
 * The band exists to answer four questions before a manager reads anything
 * else, so what is pinned is that each of the four is the PLATFORM's figure —
 * rendered from its exact decimal string, in the organization's currency, with
 * nothing summed and nothing converted on the way.
 *
 * The other half is the vessel, and it carries the ruling LACTEVA-MOBILE-007
 * settled and the architect accepted: a vessel is a measurement, a measurement
 * needs a scale, and with nothing to be full of none is drawn at all.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardHero, MilkVessel } from "@/components/dashboard-hero";

const FULL = {
  dateLine: "2026-08-21 to 2026-08-27",
  centresCollecting: 3,
  centresTotal: 3,
  litres: 1184.5,
  fill: 0.71,
  farmers: 107,
  payable: "54880.00",
  payableCurrency: "INR",
  received: "12340.00",
  receivedCurrency: "INR",
  // D-21: the unit comes WITH the figure, from the platform.
  unit: "kg",
};

describe("the hero band", () => {
  it("leads with the four figures an owner opens the page for", () => {
    render(<DashboardHero {...FULL} />);
    // Grouped, and to the platform's own decimals — not rounded, not
    // re-derived.
    expect(screen.getByText("1,184.5")).toBeInTheDocument();
    expect(screen.getByText("107")).toBeInTheDocument();
    expect(screen.getByText("54,880.00")).toBeInTheDocument();
    expect(screen.getByText("12,340.00")).toBeInTheDocument();
    expect(screen.getByText("collected")).toBeInTheDocument();
    expect(screen.getByText("receivables collected")).toBeInTheDocument();
  });

  it("says which window the figures cover, in the platform's own dates", () => {
    render(<DashboardHero {...FULL} />);
    expect(screen.getByText("2026-08-21 to 2026-08-27")).toBeInTheDocument();
  });

  it("says how many centres are collecting, in words as well as a dot", () => {
    render(<DashboardHero {...FULL} />);
    // Never colour alone: the dot is the fast signal and the sentence is the
    // one that survives not seeing it.
    expect(screen.getByRole("status")).toHaveTextContent(
      "3 of 3 centres collecting",
    );
  });

  it("shows nothing rather than a zero when the platform said nothing", () => {
    // A dashboard whose report failed must not claim the dairy collected 0 L.
    render(
      <DashboardHero
        dateLine="2026-08-27 to 2026-08-27"
        centresCollecting={null}
        centresTotal={null}
        litres={null}
        unit={null}
        fill={null}
        farmers={null}
        payable={null}
        payableCurrency={null}
        received={null}
        receivedCurrency={null}
      />,
    );
    expect(screen.getAllByText("—")).toHaveLength(4);
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("the vessel", () => {
  it("fills to the fraction it was given, and reports it", () => {
    render(<MilkVessel fill={0.71} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "71%");
    expect(screen.getByTestId("vessel-fill")).toHaveStyle({ height: "71%" });
  });

  it("is not drawn at all when there is no scale to measure against", () => {
    // The LACTEVA-MOBILE-007 ruling, on this surface: an empty vessel beside a
    // real figure says "almost nothing came", and filling one against a number
    // the browser invented would be worse.
    render(<DashboardHero {...FULL} fill={null} />);
    expect(screen.queryByTestId("vessel-fill")).toBeNull();
    // The figure itself is untouched.
    expect(screen.getByText("1,184.5")).toBeInTheDocument();
  });

  it("clamps rather than overflowing when the day beat its own peak", () => {
    render(<MilkVessel fill={1.4} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "100%");
  });

  it("draws an empty vessel for a day that has not started", () => {
    // Zero is a legitimate reading — the scale exists, the milk has not
    // arrived — and is a different thing from having no scale at all.
    render(<MilkVessel fill={0} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "0%");
  });

  it("animates through the class the reduced-motion rule can reach", () => {
    // `prefers-reduced-motion` is honoured globally in `globals.css`, which
    // collapses every animation to 1ms. That only works if the movement is a
    // CLASS rather than an inline transition, so this pins the seam.
    render(<MilkVessel fill={0.5} />);
    expect(screen.getByTestId("vessel-fill").className).toContain(
      "lacteva-vessel",
    );
  });
});
