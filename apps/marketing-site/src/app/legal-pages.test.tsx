import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LeadForm } from "@/components/lead-form";
import PrivacyPolicyPage from "./privacy-policy/page";
import TermsPage from "./terms/page";

/**
 * PRE-LAUNCH-002. Beyond rendering, these tests pin the DRAFT status:
 * the unresolved legal facts must stay visible as explicit placeholders
 * until the owner and counsel supply real values. Resolving one is a
 * conscious act — update the page AND the count here together.
 */
describe("privacy policy (PRE-LAUNCH-002)", () => {
  it("renders with title and last-updated date", () => {
    render(<PrivacyPolicyPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /lacteva privacy policy/i,
    );
    expect(screen.getByText(/last updated: 15 august 2026/i)).toBeInTheDocument();
  });

  it("describes exactly what the forms collect", () => {
    render(<PrivacyPolicyPage />);
    expect(screen.getByText(/phone number \(optional\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(/whether your request is for a demo or a free trial/i),
    ).toBeInTheDocument();
  });

  it("keeps unresolved legal facts as explicit placeholders", () => {
    const { container } = render(<PrivacyPolicyPage />);
    const placeholders = [...container.querySelectorAll("span")].filter((s) =>
      /^\[.*\]$/.test(s.textContent?.trim() ?? ""),
    );
    // Entity (x2), privacy email, address.
    expect(placeholders.length).toBe(4);
  });
});

describe("terms (PRE-LAUNCH-002)", () => {
  it("renders with title and the 21 numbered sections", () => {
    render(<TermsPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /lacteva terms & conditions/i,
    );
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBe(21);
  });

  it("describes the trial honestly — request, review, team setup, 30 days", () => {
    render(<TermsPage />);
    const trial = screen.getByRole("heading", { name: /6\. free trial/i })
      .parentElement?.textContent;
    expect(trial).toMatch(/30-day free trial/i);
    expect(trial).toMatch(/provisioned by our team rather than automatically/i);
  });

  it("keeps counsel-required clauses as explicit placeholders", () => {
    render(<TermsPage />);
    expect(
      screen.getByText(/\[LEGAL REVIEW REQUIRED — LIMITATION OF LIABILITY LANGUAGE\]/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/\[LEGAL REVIEW REQUIRED — INDEMNIFICATION LANGUAGE\]/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/\[GOVERNING LAW AND JURISDICTION — BUSINESS\/LEGAL DECISION\s+REQUIRED\]/),
    ).toBeInTheDocument();
  });
});

describe("form privacy notice (PRE-LAUNCH-002)", () => {
  it("links both legal pages next to the submit action", () => {
    render(<LeadForm />);
    expect(screen.getByRole("link", { name: /privacy policy/i })).toHaveAttribute(
      "href",
      "/privacy-policy",
    );
    expect(screen.getByRole("link", { name: /terms/i })).toHaveAttribute(
      "href",
      "/terms",
    );
  });
});
