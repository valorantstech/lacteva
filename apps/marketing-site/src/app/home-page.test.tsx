import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "./page";

describe("home page (MKT-004C)", () => {
  it("leads with the connected-operations positioning", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /run your dairy operations as one connected business/i,
    );
  });

  it("routes the trial and demo CTAs to their pages", () => {
    render(<HomePage />);
    const trialLinks = screen.getAllByRole("link", {
      name: /start free trial/i,
    });
    expect(trialLinks.length).toBeGreaterThan(0);
    for (const link of trialLinks) {
      expect(link).toHaveAttribute("href", "/start-free-trial");
    }
    const demoLinks = screen.getAllByRole("link", { name: /book a demo/i });
    expect(demoLinks.length).toBeGreaterThan(0);
    for (const link of demoLinks) {
      expect(link).toHaveAttribute("href", "/request-demo");
    }
  });

  it("states the trial honestly — a person sets it up", () => {
    render(<HomePage />);
    expect(
      screen.getByText(/30-day free trial — our team sets up your environment/i),
    ).toBeInTheDocument();
  });

  it("renders the full connected lifecycle in order", () => {
    render(<HomePage />);
    const stages = [
      "Procurement",
      "Collection",
      "Customers",
      "Delivery",
      "Billing",
      "Payments",
      "Settlements",
      "Reports",
    ];
    const text = document.body.textContent ?? "";
    let cursor = -1;
    for (const stage of stages) {
      const index = text.indexOf(stage, cursor + 1);
      expect(index, `${stage} appears after its predecessor`).toBeGreaterThan(
        cursor,
      );
      cursor = index;
    }
  });

  it("never fabricates product UI — screenshots are real or say so", () => {
    render(<HomePage />);
    // With no captures on disk yet, every ProductShot must render the
    // explicit placeholder, not an invented dashboard.
    expect(
      screen.getAllByText(/placeholder — to be replaced with a capture/i)
        .length,
    ).toBeGreaterThan(0);
  });
});
