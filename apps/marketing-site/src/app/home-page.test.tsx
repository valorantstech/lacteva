import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "./page";

describe("home page (MKT-004C · hero per LACTEVA-MARKETING-002)", () => {
  it("leads with the approved hero headline", () => {
    render(<HomePage />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent(/every drop,/i);
    expect(heading).toHaveTextContent(/accounted for\./i);
  });

  it("routes the hero CTAs — trial, and the ruled substitution to /product", () => {
    render(<HomePage />);
    // The board's "Watch the counter flow" has nothing real to open, so the
    // work order's fallback ships: "See how it works" → /product.
    expect(
      screen.getByRole("link", { name: /start your dairy's trial/i }),
    ).toHaveAttribute("href", "/start-free-trial");
    expect(
      screen.getByRole("link", { name: /see how it works/i }),
    ).toHaveAttribute("href", "/product");
    expect(screen.queryByText(/watch the counter flow/i)).not.toBeInTheDocument();
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

  it("carries the board's proof row and module chips", () => {
    render(<HomePage />);
    for (const fact of ["Offline-first", "FAT-banded rates", "Parchi to payment"]) {
      expect(screen.getByText(fact)).toBeInTheDocument();
    }
    expect(screen.getByText(/runs the whole dairy:/i)).toBeInTheDocument();
    expect(screen.getByText("Quality")).toBeInTheDocument();
    expect(screen.getByText("Invoices")).toBeInTheDocument();
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
    // LACTEVA-MARKETING-006: the captures exist, so every ProductShot on
    // the home renders a REAL image (alt-labelled), and no placeholder
    // remains. If a capture file disappears, the honest placeholder comes
    // back — either state passes the fabrication rule, a mock never would.
    const shots = screen.getAllByRole("img", { name: /—|handset/ });
    expect(shots.length).toBe(4);
    for (const shot of shots) {
      // next/image wraps the path in its optimizer URL — the screenshots
      // segment survives, URL-encoded.
      expect(shot).toHaveAttribute("src", expect.stringContaining("screenshots"));
    }
    expect(
      screen.queryByText(/placeholder — to be replaced with a capture/i),
    ).not.toBeInTheDocument();
  });
});
