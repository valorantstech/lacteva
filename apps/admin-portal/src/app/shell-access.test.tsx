/**
 * The shell keeps people out of areas their role cannot use (P0-UX-001).
 *
 * Found in the browser walkthrough, not by reading: a DRIVER deep-linking to
 * `/routes` was shown the office's "Add a route / vehicle / driver" forms with
 * a raw permission-key error where the data should be. The platform refused
 * everything — security held — but the page had promised what the role cannot
 * do. The shell now renders the calm refusal instead, in the dashboard
 * banner's own words, and tells a driver where their work actually lives.
 *
 * Client-side courtesy only: the server's guards are the security, and they
 * were verified to hold without this.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pathname = { current: "/routes" };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => pathname.current,
}));

import { AppShell } from "@/components/app-shell";
import * as api from "@/lib/api";

const SESSION_BASE = {
  authenticated: true as const,
  acting_tenant_id: null,
  user: { id: "u1", email: "who@dairy.example", full_name: "Who Ever", status: "active" },
  tenant_id: "org-1",
  organization: {
    id: "org-1",
    name: "Kilima",
    slug: "kilima",
    currency_code: "KES",
    timezone: "Africa/Nairobi",
    default_language: "en",
    supported_languages: ["en"],
  },
  membership: null,
  roles: [],
  center_scope: null,
  customer_id: null,
};

function stubSession(permissions: string[]) {
  vi.spyOn(api, "getSession").mockResolvedValue({
    ...SESSION_BASE,
    permissions,
  } as never);
}

beforeEach(() => {
  vi.restoreAllMocks();
  pathname.current = "/routes";
});

describe("the shell's access gate", () => {
  it("shows a driver the calm refusal on an office page, and points at the phone", async () => {
    stubSession(["logistics.run.execute"]);
    render(
      <AppShell>
        <div>OFFICE FORMS</div>
      </AppShell>,
    );

    expect(
      await screen.findByText("This area is not part of your access."),
    ).toBeInTheDocument();
    // The driver-specific sentence: their work genuinely lives elsewhere.
    expect(screen.getByText(/Lacteva mobile app/)).toBeInTheDocument();
    // And the office scaffolding is NOT offered.
    expect(screen.queryByText("OFFICE FORMS")).toBeNull();
  });

  it("shows a non-driver the refusal without the mobile hint", async () => {
    pathname.current = "/settlements";
    stubSession(["collection.transaction.read"]);
    render(
      <AppShell>
        <div>SETTLEMENT FORMS</div>
      </AppShell>,
    );

    expect(
      await screen.findByText("This area is not part of your access."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Lacteva mobile app/)).toBeNull();
    expect(screen.queryByText("SETTLEMENT FORMS")).toBeNull();
  });

  it("renders the page for a role that holds the permission", async () => {
    stubSession(["logistics.route.read", "logistics.run.read"]);
    render(
      <AppShell>
        <div>ROUTES PAGE</div>
      </AppShell>,
    );

    expect(await screen.findByText("ROUTES PAGE")).toBeInTheDocument();
    expect(screen.queryByText("This area is not part of your access.")).toBeNull();
  });

  it("a detail path is gated by its parent entry", async () => {
    pathname.current = "/customers/abc-123";
    stubSession(["logistics.run.execute"]);
    render(
      <AppShell>
        <div>CUSTOMER DETAIL</div>
      </AppShell>,
    );

    expect(
      await screen.findByText("This area is not part of your access."),
    ).toBeInTheDocument();
    expect(screen.queryByText("CUSTOMER DETAIL")).toBeNull();
  });

  it("the dashboard stays open to any signed-in role", async () => {
    pathname.current = "/";
    stubSession(["logistics.run.execute"]);
    render(
      <AppShell>
        <div>DASHBOARD</div>
      </AppShell>,
    );

    await waitFor(() =>
      expect(screen.getByText("DASHBOARD")).toBeInTheDocument(),
    );
  });
});
