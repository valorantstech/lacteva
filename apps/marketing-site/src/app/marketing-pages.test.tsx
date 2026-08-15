import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ProductPage from "./product/page";
import SolutionsPage from "./solutions/page";

describe("product page (MKT-004D)", () => {
  it("leads with the connected hero", () => {
    render(<ProductPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /everything your dairy operation needs to stay connected/i,
    );
  });

  it("presents exactly the five approved capability groups", () => {
    render(<ProductPage />);
    for (const group of ["Procure", "Operate", "Serve", "Bill", "Understand"]) {
      expect(
        screen.getByRole("heading", { level: 3, name: group }),
      ).toBeInTheDocument();
    }
  });

  it("renders the connected lifecycle", () => {
    render(<ProductPage />);
    expect(screen.getByText("Settlements")).toBeInTheDocument();
  });
});

describe("solutions page (MKT-004D)", () => {
  const AUDIENCES = [
    "Dairy companies",
    "Cooperatives",
    "Milk collection organizations",
    "Milk distributors",
    "Growing dairy businesses",
    "Enterprise dairy operations",
  ];

  it("covers all six audiences as sections with anchors", () => {
    render(<SolutionsPage />);
    for (const audience of AUDIENCES) {
      expect(
        screen.getByRole("heading", { level: 2, name: audience }),
      ).toBeInTheDocument();
    }
    const anchors = document.querySelectorAll("article[id]");
    expect(anchors.length).toBe(6);
  });

  it("gives each audience its own story, not a template", () => {
    render(<SolutionsPage />);
    // The jump-nav links to every anchor.
    const nav = screen.getByRole("navigation", {
      name: /solutions on this page/i,
    });
    expect(nav.querySelectorAll("a[href^='#']").length).toBe(6);
    // No two problem statements may be identical.
    const problems = [
      ...document.querySelectorAll("article > div:first-of-type > p:first-of-type"),
    ].map((p) => p.textContent);
    expect(problems.length).toBe(6);
    expect(new Set(problems).size).toBe(problems.length);
  });
});
