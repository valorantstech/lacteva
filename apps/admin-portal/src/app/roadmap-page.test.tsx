/**
 * The roadmap visibility page (P0-PRODUCT-VISIBILITY-001).
 *
 * The product's honesty rule is that a Coming-Soon capability must never be
 * mistaken for a shipped one. This page exists to keep those two categories
 * visibly apart, so the tests defend exactly that separation — not the
 * vocabulary of any one row:
 *   1. the page calls no API and needs no session (it cannot leak or fabricate
 *      data because it fetches none),
 *   2. an "available today" capability is a real link to its real page,
 *   3. a roadmap capability is inert — labelled Coming soon / Enterprise and
 *      NOT a control that goes anywhere.
 * A page that merely listed features would pass a weaker test; what is asserted
 * is that the roadmap items cannot be clicked into a promise.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/roadmap",
}));

import RoadmapPage from "@/app/roadmap/page";

describe("the roadmap page", () => {
  it("fetches nothing — it is informational, not data-backed", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<RoadmapPage />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("keeps available-today and roadmap in separate, labelled sections", () => {
    render(<RoadmapPage />);
    for (const title of ["Available today", "Coming soon", "Enterprise", "Future options"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    // The header spells out that everything below "today" is not yet available.
    expect(
      screen.getByText(/on the roadmap and is NOT available yet/i),
    ).toBeInTheDocument();
  });

  it("makes an available capability a real link to its real page", () => {
    render(<RoadmapPage />);
    const rateCards = screen.getByText("Rate cards").closest("a");
    expect(rateCards).not.toBeNull();
    expect(rateCards).toHaveAttribute("href", "/rate-cards");
  });

  it("leaves every roadmap capability inert — no link, a Coming-soon label", () => {
    render(<RoadmapPage />);
    // A V1 item: labelled, not clickable.
    const messaging = screen.getByText("Messaging (WhatsApp / SMS)");
    expect(messaging.closest("a")).toBeNull();
    // An enterprise item: labelled Enterprise, not clickable.
    const sap = screen.getByText("SAP / ERP integration");
    expect(sap.closest("a")).toBeNull();
    // The Coming-soon and Enterprise labels are actually present.
    expect(screen.getAllByText(/Coming soon/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Enterprise").length).toBeGreaterThan(0);
  });

  it("does not invent AI — it names the honest status of ML", () => {
    render(<RoadmapPage />);
    const ai = screen.getByText("Advanced AI");
    expect(ai.closest("a")).toBeNull();
    expect(
      screen.getByText(/No AI vendor and no ML model exist in the product today/i),
    ).toBeInTheDocument();
  });
});
