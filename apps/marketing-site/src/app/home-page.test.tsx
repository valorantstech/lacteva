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

  // The commitments band (held pricing claims) was removed in MKT-004B;
  // the connected-operation story is the differentiator that replaced it.
  it("tells the connected-operations story", () => {
    render(<HomePage />);
    expect(screen.getByText(/one connected operation/i)).toBeInTheDocument();
  });
});
