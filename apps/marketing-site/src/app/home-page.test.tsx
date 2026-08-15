import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "./page";

describe("home page", () => {
  it("leads with the demo-able promise", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { level: 1 }),
    ).toHaveTextContent(/collect milk offline/i);
  });

  it("routes both hero actions to real pages", () => {
    render(<HomePage />);
    const demoLinks = screen.getAllByRole("link", { name: /request a demo/i });
    expect(demoLinks.length).toBeGreaterThan(0);
    for (const link of demoLinks) {
      expect(link).toHaveAttribute("href", "/request-demo");
    }
    expect(
      screen.getByRole("link", { name: /see how it works/i }),
    ).toHaveAttribute("href", "/product");
  });

  it("states the pricing commitments that are permanent", () => {
    render(<HomePage />);
    expect(screen.getByText(/farmers never pay/i)).toBeInTheDocument();
  });
});
