/**
 * The shell and the session it holds (WO-79 · LACTEVA-ADMIN-023).
 *
 * The owner, back after a fortnight away, saw the full signed-in shell —
 * organisation chip, their own name, Sign out, the whole rail — wrapped
 * around a sign-in form asking for their password. Two halves of one
 * defect, and a third by another road:
 *
 *  3. /login must wear the signed-out chrome WHATEVER the probe answers.
 *     The sign-in page's own redirect (part 2) makes that state last one
 *     probe, but one probe is long enough to paint the screenshot.
 *  5. A session that has ENDED — the platform refused the refresh — must
 *     land on the sign-in page, not on the dashboard's signed-out state with
 *     a small "Sign in" link (the WO-59 defect, reached differently).
 *     `unreachable` is an outage, not a sign-out, and stays put (WO-73).
 *
 * No loop: part 2 sends /login → "/" only on `authenticated: true`; part 5
 * sends "/" → /login only on `authenticated: false`; the same probe cannot
 * answer both, and `unreachable` triggers neither.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pathname = { current: "/settlements" };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  usePathname: () => pathname.current,
}));

const assign = vi.fn();
function at(path: string, search = "") {
  pathname.current = path;
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, pathname: path, search, assign },
  });
}

import { AppShell } from "@/components/app-shell";
import * as api from "@/lib/api";

const PRIYA = {
  authenticated: true as const,
  acting_tenant_id: null,
  user: {
    id: "u1",
    email: "manager@lacteva-india.example.com",
    full_name: "Priya Raghavan",
    status: "active",
  },
  tenant_id: "org-1",
  organization: {
    id: "org-1",
    name: "Lacteva India Demo",
    slug: "lacteva-india",
    currency_code: "INR",
    timezone: "Asia/Kolkata",
    default_language: "en",
    supported_languages: ["en"],
  },
  membership: null,
  roles: [{ name: "tenant-admin", center_id: null }],
  center_scope: null,
  customer_id: null,
  permissions: ["*"],
};

beforeEach(() => {
  vi.restoreAllMocks();
  assign.mockClear();
});

describe("part 3 — /login never wears the signed-in chrome", () => {
  it("draws the rail and the person's name on the dashboard", async () => {
    at("/");
    vi.spyOn(api, "getSession").mockResolvedValue(PRIYA as never);
    render(
      <AppShell>
        <div>DASHBOARD</div>
      </AppShell>,
    );
    expect(await screen.findByText("Priya Raghavan")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("draws NEITHER on /login, whatever the probe says", async () => {
    at("/login");
    const probe = vi.spyOn(api, "getSession").mockResolvedValue(PRIYA as never);
    render(
      <AppShell>
        <div>SIGN-IN FORM</div>
      </AppShell>,
    );
    await waitFor(() => expect(probe).toHaveBeenCalled());
    // Let the answer land, then look: the form, and none of the chrome.
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.getByText("SIGN-IN FORM")).toBeInTheDocument();
    expect(screen.queryByText("Priya Raghavan")).toBeNull();
    expect(screen.queryByText("Lacteva India Demo")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    // And the shell does not navigate from /login — that is the page's job.
    expect(assign).not.toHaveBeenCalled();
  });
});

describe("part 5 — a session that has ended lands on the sign-in page", () => {
  it("goes to /login carrying where they were", async () => {
    at("/settlements");
    vi.spyOn(api, "getSession").mockResolvedValue({ authenticated: false });
    render(
      <AppShell>
        <div>SETTLEMENTS</div>
      </AppShell>,
    );
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/login?next=%2Fsettlements"),
    );
  });

  it("carries the query string too, through the guard's own safeNext", async () => {
    at("/settlements", "?status=finalized");
    vi.spyOn(api, "getSession").mockResolvedValue({ authenticated: false });
    render(<AppShell><div /></AppShell>);
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "/login?next=%2Fsettlements%3Fstatus%3Dfinalized",
      ),
    );
  });

  it("an outage is not a sign-out: unreachable stays put", async () => {
    at("/settlements");
    const probe = vi
      .spyOn(api, "getSession")
      .mockResolvedValue({ authenticated: false, unreachable: true });
    render(<AppShell><div>SETTLEMENTS</div></AppShell>);
    await waitFor(() => expect(probe).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(assign).not.toHaveBeenCalled();
    expect(screen.getByText("SETTLEMENTS")).toBeInTheDocument();
  });

  it("a probe that throws is an outage too, not a sign-out", async () => {
    at("/settlements");
    const probe = vi.spyOn(api, "getSession").mockRejectedValue(new TypeError("fetch failed"));
    render(<AppShell><div>SETTLEMENTS</div></AppShell>);
    await waitFor(() => expect(probe).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(assign).not.toHaveBeenCalled();
  });

  it.each(["/login", "/reset-password", "/accept-invitation"])(
    "never navigates away from %s — the public routes are where a stranger belongs",
    async (path) => {
      at(path);
      const probe = vi.spyOn(api, "getSession").mockResolvedValue({ authenticated: false });
      render(<AppShell><div>PUBLIC</div></AppShell>);
      await waitFor(() => expect(probe).toHaveBeenCalled());
      await new Promise((r) => setTimeout(r, 0));
      expect(assign).not.toHaveBeenCalled();
      expect(screen.getByText("PUBLIC")).toBeInTheDocument();
    },
  );

  it("a live session on the dashboard is not sent anywhere (the other half of no-loop)", async () => {
    at("/");
    vi.spyOn(api, "getSession").mockResolvedValue(PRIYA as never);
    render(<AppShell><div>DASHBOARD</div></AppShell>);
    expect(await screen.findByText("Priya Raghavan")).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
