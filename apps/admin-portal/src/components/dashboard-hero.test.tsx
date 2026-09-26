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

import { DashboardHero, MilkVessel, ShopHero } from "@/components/dashboard-hero";

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

/**
 * WO-104 (WO-85 §7): the shop's morning. On the sales-only Patel Dairy Shop
 * the dairy hero read "0.0 collected · 0 farmers delivered · 0.00 payable
 * accrued · 0.00 receivables collected" and "1 of 1 centres collecting" —
 * five figures about milk a shop never buys.
 */
describe("the shop hero", () => {
  const SHOP = {
    dateLine: "2026-09-26 to 2026-09-26",
    round: { delivered: 38, remaining: 9, skipped: 2 },
    delivered: "412.500",
    unit: "L",
    billsOpen: 14,
    billsAmount: "18650.00",
    received: "3200.00",
    currency: "INR",
  };

  it("leads with today's round, today's milk, the bills still open and today's cash", () => {
    render(<ShopHero {...SHOP} />);
    expect(screen.getByRole("status")).toHaveTextContent("38 delivered · 9 to go · 2 skipped");
    expect(screen.getByText("38 / 49")).toBeInTheDocument();
    expect(screen.getByText("today's round")).toBeInTheDocument();
    expect(screen.getByText("412.5")).toBeInTheDocument();
    expect(screen.getByText("milk delivered today")).toBeInTheDocument();
    expect(screen.getByText("18,650.00")).toBeInTheDocument();
    expect(screen.getByText("bills outstanding · 14 open")).toBeInTheDocument();
    expect(screen.getByText("3,200.00")).toBeInTheDocument();
    expect(screen.getByText("money received today")).toBeInTheDocument();
  });

  it("shows NO collection figure — not collected, not farmers, not payable, not centres", () => {
    const { container } = render(<ShopHero {...SHOP} />);
    const text = container.textContent ?? "";
    for (const word of ["collected", "farmers", "payable", "centres collecting", "receivables"]) {
      expect(text, word).not.toContain(word);
    }
    expect(container.querySelector('[data-testid="vessel-fill"]')).toBeNull();
  });

  it("says when no round is planned, and shows dashes rather than zeroes for what it does not know", () => {
    render(
      <ShopHero
        dateLine="2026-09-26 to 2026-09-26"
        round={null}
        delivered={null}
        unit={null}
        billsOpen={null}
        billsAmount={null}
        received={null}
        currency={null}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("No round planned today");
    expect(screen.getAllByText("—")).toHaveLength(4);
    expect(screen.getByText("bills outstanding")).toBeInTheDocument();
  });
});
