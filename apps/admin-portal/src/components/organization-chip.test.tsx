/**
 * Say which dairy this is (WO-60 · LACTEVA-ADMIN-020).
 *
 * The owner reported "KES on some pages, INR on others". The currency was
 * CORRECT — the demo runs a Kenyan dairy and an Indian one, and each shows
 * its own money. What the report exposed is that the portal never said WHICH
 * organization you were in: the chip rendered the literal word
 * "Organization", the identity line said "Organization member", and a
 * platform administrator acting in a tenant saw a truncated UUID.
 *
 * For a multi-tenant product that question has to be answerable at a glance.
 * For a demonstration it is the difference between a Kenyan and an Indian
 * dairy on the screen the client is looking at.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
  usePathname: () => "/",
}));

import { AppShell } from "@/components/app-shell";

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

const ORGANIZATION = {
  id: "org-1",
  name: "Lacteva Demo Cooperative",
  slug: "lacteva-demo",
  country_code: "KE",
  currency_code: "KES",
  currency_symbol: "KSh",
  timezone: "Africa/Nairobi",
  default_language: "en-KE",
  supported_languages: ["en-KE"],
  languages: [],
};

function signedInAs(session: Record<string, unknown>) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/auth/session"))
      return json({ authenticated: true, ...session });
    return json({ items: [], total: 0, limit: 25, offset: 0 });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

const MEMBER = {
  tenant_id: "org-1",
  acting_tenant_id: null,
  organization: ORGANIZATION,
  permissions: ["*"],
  roles: [{ name: "CENTRE_MANAGER", description: "", center_id: null }],
  user: { id: "u1", email: "priya@kilima.example", full_name: "Priya Raghavan" },
};

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("the chip says which dairy this is", () => {
  it("renders the organization's name for a member", async () => {
    signedInAs(MEMBER);
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(
      await screen.findByText("Lacteva Demo Cooperative"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();
  });

  it("keeps the full name reachable when it is too long to show", async () => {
    signedInAs({
      ...MEMBER,
      organization: {
        ...ORGANIZATION,
        name: "Kilima Hill Smallholder Dairy Farmers Co-operative Society Limited",
      },
    });
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    const chip = await screen.findByText(
      "Kilima Hill Smallholder Dairy Farmers Co-operative Society Limited",
    );
    expect(chip).toHaveClass("truncate");
    expect(chip.parentElement).toHaveAttribute(
      "title",
      "Kilima Hill Smallholder Dairy Farmers Co-operative Society Limited",
    );
  });

  it("offers no chevron, because there is no menu behind it", async () => {
    // Same ruling as WO-51b's disabled button: a control that looks
    // interactive and is not tells the reader something untrue.
    signedInAs(MEMBER);
    const { container } = render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    // Wait for the signed-in chrome, or this asserts about an empty shell.
    await screen.findByText("Lacteva Demo Cooperative");
    expect(container.querySelector(".lucide-chevron-down")).toBeNull();
  });
});

describe("the identity line says what this person is", () => {
  it("shows the role, not 'Organization member'", async () => {
    signedInAs(MEMBER);
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(await screen.findByText("Centre Manager")).toBeInTheDocument();
    expect(screen.queryByText("Organization member")).not.toBeInTheDocument();
  });

  it("lists both when somebody holds two roles", async () => {
    signedInAs({
      ...MEMBER,
      roles: [
        { name: "CENTRE_MANAGER", description: "", center_id: null },
        { name: "COLLECTION_OPERATOR", description: "", center_id: "c1" },
      ],
    });
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(
      await screen.findByText("Centre Manager · Collection Operator"),
    ).toBeInTheDocument();
  });

  it("falls back honestly for a member holding no named role", async () => {
    signedInAs({ ...MEMBER, roles: [] });
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(await screen.findByText("Organization member")).toBeInTheDocument();
  });

  it("keeps 'Platform administrator' for a platform session", async () => {
    signedInAs({
      ...MEMBER,
      tenant_id: null,
      acting_tenant_id: null,
      organization: null,
      roles: [],
    });
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(await screen.findByText("Platform administrator")).toBeInTheDocument();
  });
});

describe("a platform administrator acting in a tenant", () => {
  it("sees the tenant's NAME, not a truncated UUID", async () => {
    signedInAs({
      ...MEMBER,
      tenant_id: null,
      acting_tenant_id: "8f3a2b1c-0000-4000-8000-000000000000",
      organization: ORGANIZATION,
      roles: [],
    });
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(
      await screen.findByText("acting in Lacteva Demo Cooperative"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/8f3a2b1c…/)).not.toBeInTheDocument();
  });

  it("still says something when the tenant's name has not arrived yet", async () => {
    signedInAs({
      ...MEMBER,
      tenant_id: null,
      acting_tenant_id: "8f3a2b1c-0000-4000-8000-000000000000",
      organization: null,
      roles: [],
    });
    render(
      <AppShell>
        <p>page</p>
      </AppShell>,
    );
    expect(await screen.findByText(/acting in 8f3a2b1c…/)).toBeInTheDocument();
  });
});
