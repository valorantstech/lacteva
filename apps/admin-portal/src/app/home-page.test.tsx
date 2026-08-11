/**
 * DASH-001 — the home page crashed for signed-out visitors.
 *
 * `refresh()` fetched /health/ready and cast the body to `Readiness` without
 * checking the status. A 401 answers with a problem document — no `checks` —
 * so the render reached `Object.entries(undefined)` and threw "Cannot convert
 * undefined or null to object", taking the whole page down. A cast is a claim,
 * not a check.
 *
 * DEMO-001 rebuilt this page on the platform's own `/v1/reports/*` aggregates
 * and restyled it. The GUARANTEES below are unchanged — do not crash on a
 * problem document, ask for nothing tenant-scoped while signed out, show the
 * readiness checks, and report an unreachable platform rather than trusting
 * its body. Only the wording the assertions match on moved with the copy.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

import Home from "@/app/page";

function routeFetch(handler: (url: string) => Response) {
  const spy = vi.fn(async (input: RequestInfo | URL) => handler(String(input)));
  vi.stubGlobal("fetch", spy);
  return spy;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("home page", () => {
  it("does not crash when the platform answers 401 to everything", async () => {
    routeFetch((url) =>
      url.includes("/api/auth/session")
        ? json({ authenticated: false })
        : json({ title: "unauthorized", detail: "Authentication is required.", status: 401 }, 401),
    );

    // Rendering at all is the assertion: the old build threw here.
    render(<Home />);
    expect(await screen.findByText(/sign in to see today/i)).toBeInTheDocument();
  });

  it("asks for nothing tenant-scoped while signed out", async () => {
    const fetchSpy = routeFetch((url) =>
      url.includes("/api/auth/session")
        ? json({ authenticated: false })
        : json({ title: "unauthorized" }, 401),
    );

    render(<Home />);
    await screen.findByText(/sign in to see today/i);
    await new Promise((r) => setTimeout(r, 50));

    const asked = fetchSpy.mock.calls.map(([u]) => String(u));
    expect(asked.some((u) => u.includes("/v1/settlements"))).toBe(false);
    expect(asked.some((u) => u.includes("/health/ready"))).toBe(false);
  });

  it("shows the dashboard and the readiness checks when signed in", async () => {
    routeFetch((url) => {
      if (url.includes("/api/auth/session")) {
        return json({
          authenticated: true,
          user: { id: "u1", email: "boss@kilima.example", full_name: "Boss", locale: "en", is_active: true },
          tenant_id: "org-1",
          permissions: [],
        });
      }
      if (url.includes("/health/ready")) {
        return json({ status: "ok", checks: { database: true, redis: true } });
      }
      return json({ total: 7 });
    });

    render(<Home />);
    await waitFor(() => expect(screen.getByText("database")).toBeInTheDocument());
    expect(screen.getByText("redis")).toBeInTheDocument();
    expect(screen.queryByText(/sign in to see today/i)).not.toBeInTheDocument();
  });

  it("reports an unhealthy readiness response instead of trusting its body", async () => {
    routeFetch((url) => {
      if (url.includes("/api/auth/session")) {
        return json({
          authenticated: true,
          user: { id: "u1", email: "b@e.example", full_name: "B", locale: "en", is_active: true },
          tenant_id: "org-1",
          permissions: [],
        });
      }
      if (url.includes("/health/ready")) return json({ title: "unauthorized" }, 401);
      return json({ total: 0 });
    });

    render(<Home />);
    await waitFor(() => expect(screen.getByText(/unreachable/i)).toBeInTheDocument());
  });
});
