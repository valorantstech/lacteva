import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LeadForm } from "@/components/lead-form";
import { SiteHeader } from "@/components/site-header";
import LoginPage from "./login/page";
import PricingPage from "./pricing/page";
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

describe("pricing page (MKT-004E)", () => {
  it("sells the trial model, not invented price cards", () => {
    render(<PricingPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /simple to start\. ready to scale\./i,
    );
    // Five trial steps, in a list.
    expect(
      screen.getByRole("heading", { name: /start with a 30-day free trial/i }),
    ).toBeInTheDocument();
    expect(document.querySelectorAll("ol > li").length).toBe(5);
  });

  it("contains no price — pricing is not finalized", () => {
    render(<PricingPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/[$₹€£]\s?\d/);
    expect(text).not.toMatch(/\d+\s*\/\s*(month|mo|year|yr)/i);
    expect(text).not.toMatch(/per (user|seat|centre|center|litre|liter)/i);
  });

  it("routes both CTAs correctly", () => {
    render(<PricingPage />);
    for (const link of screen.getAllByRole("link", { name: /start free trial/i })) {
      expect(link).toHaveAttribute("href", "/start-free-trial");
    }
    for (const link of screen.getAllByRole("link", { name: /book a demo/i })) {
      expect(link).toHaveAttribute("href", "/request-demo");
    }
  });
});

describe("site header (PRE-LAUNCH-001)", () => {
  it("offers Login in both the desktop and mobile navigation", () => {
    render(<SiteHeader />);
    const logins = screen.getAllByRole("link", { name: /^login$/i });
    // One sm+ link and one inside the mobile nav row.
    expect(logins.length).toBe(2);
    for (const link of logins) {
      expect(link).toHaveAttribute("href", "/login");
    }
    const mobileNav = screen.getByRole("navigation", { name: /main mobile/i });
    expect(mobileNav.querySelector('a[href="/login"]')).not.toBeNull();
  });
});

describe("login page (MKT-004E)", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_PORTAL_URL;
  });

  it("explains itself when no portal URL is configured — never invents one", () => {
    render(<LoginPage />);
    expect(screen.getByText(/not configured/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /continue to login/i })).toBeNull();
  });

  it("hands over to the configured portal", () => {
    process.env.NEXT_PUBLIC_PORTAL_URL = "https://portal.example";
    render(<LoginPage />);
    expect(
      screen.getByRole("link", { name: /continue to login/i }),
    ).toHaveAttribute("href", "https://portal.example");
  });
});

describe("trial lead form (MKT-004E)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits with trial intent and shows the approved, honest success copy", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "received" }), { status: 202 }),
      );
    const user = userEvent.setup();
    render(
      <LeadForm
        intent="trial"
        submitLabel="Request your free trial"
        successDetail="Thanks — your trial request has been received. Our team will review your requirements and help set up your Lacteva environment."
      />,
    );
    await user.type(screen.getByLabelText(/name/i), "Amina");
    await user.type(screen.getByLabelText(/work email/i), "amina@example.coop");
    await user.type(screen.getByLabelText(/^organization$/i), "Example Dairy");
    await user.type(screen.getByLabelText(/country/i), "Kenya");
    await user.click(
      screen.getByRole("button", { name: /request your free trial/i }),
    );
    // Honest success: received-and-reviewed, never account-created.
    expect(
      await screen.findByText(/your trial request has been received/i),
    ).toBeInTheDocument();
    const body = JSON.parse(
      (fetchSpy.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(body.intent).toBe("trial");
  });
});
