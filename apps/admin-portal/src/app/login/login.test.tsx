/**
 * PORTAL-001 / F-09 — the flow every other page depends on.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const assign = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

// jsdom's `window.location` is not assignable; replace the method itself.
Object.defineProperty(window, "location", {
  configurable: true,
  value: { ...window.location, assign },
});

import LoginPage from "@/app/login/page";

beforeEach(() => {
  push.mockClear();
  assign.mockClear();
  vi.unstubAllGlobals();
});

async function fillIn(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Email"), "manager@kilima.example");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
}

describe("signing in returns the visitor to what they asked for (WO-59)", () => {
  const at = (search: string) =>
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, search, assign },
    });

  it("lands on the page the guard interrupted", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    at("?next=%2Fsettlements%3Fstatus%3Dfinalized");
    const user = userEvent.setup();
    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/settlements?status=finalized"),
    );
  });

  it("lands on the dashboard when the next= is one somebody tampered with", async () => {
    // The other half of the open-redirect refusal: the FORM does the
    // navigating, so it re-checks rather than trusting the query string.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    at("?next=https%3A%2F%2Fevil.example%2Fsteal");
    const user = userEvent.setup();
    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
    expect(assign).not.toHaveBeenCalledWith(expect.stringContaining("evil.example"));
  });
});

describe("login page", () => {
  it("signs in and moves on", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // DEMO-010: the dashboard, not the centres list — and a FULL navigation,
    // because the app shell probes the session once when it mounts and a
    // client-side push leaves it showing signed-out chrome on a signed-in
    // page. That is not a detail: it meant signing in landed on a dashboard
    // with no navigation until the user reloaded.
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
    expect(push).not.toHaveBeenCalled();
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/auth/login");
  });

  it("shows the platform's reason when the credentials are wrong, and stays put", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "Email or password is incorrect." }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText("Email or password is incorrect."),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("tells the operator they are rate limited rather than that the password is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Too many requests. Please wait and try again.",
          }),
          {
            status: 429,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/Too many requests/)).toBeInTheDocument();
  });

  it("never writes a credential into browser storage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(assign).toHaveBeenCalled());

    // The claim is that no CREDENTIAL is written, and it is asserted directly
    // rather than through an empty-storage proxy: LACTEVA-BRAND-003 gave this
    // page one legitimate session key (the reveal's once-a-session gate), and
    // a count would have called that a security regression. Naming the secrets
    // is also the stronger test — a store holding one unrelated key still
    // fails if the password is in it.
    const written = [window.localStorage, window.sessionStorage].flatMap(
      (store) =>
        Array.from({ length: store.length }, (_, i) => {
          const key = store.key(i)!;
          return `${key}=${store.getItem(key)}`;
        }),
    );
    for (const secret of ["manager@kilima.example", "correct-horse-battery"]) {
      expect(written.join("\n")).not.toContain(secret);
    }
    // And nothing that even claims to be one.
    for (const entry of written) {
      expect(entry).not.toMatch(/password|token|secret|credential/i);
    }
  });
});

// --- DEMO-010: the organization UUID is gone from the first screen -----------

describe("signing in without knowing a tenant UUID", () => {
  it("does not ask for an organization at all", async () => {
    render(<LoginPage />);
    expect(screen.queryByLabelText(/organization/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tenant/i)).not.toBeInTheDocument();
  });

  it("sends only the credentials", async () => {
    const calls: RequestInit[] = [];
    const fetchSpy = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        if (init) calls.push(init);
        return new Response(null, { status: 204 });
      },
    );
    vi.stubGlobal("fetch", fetchSpy);
    render(<LoginPage />);

    await userEvent.type(
      screen.getByLabelText("Email"),
      "owner@kilima.example",
    );
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const body = JSON.parse(String(calls[0]?.body));
    expect(body).toEqual({
      email: "owner@kilima.example",
      password: "correct-horse",
    });
    expect(body).not.toHaveProperty("tenant_id");
  });

  it("asks which organization ONLY when the platform says the sign-in is ambiguous", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            title: "ambiguous_tenant",
            detail: "This sign-in works for more than one organization.",
          }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText("Email"), "both@dairy.example");
    await userEvent.type(screen.getByLabelText("Password"), "shared-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByLabelText("Organization")).toBeInTheDocument();
    // Both the platform's message and the field's own hint say it; one is enough.
    expect(
      screen.getAllByText(/more than one organization/i).length,
    ).toBeGreaterThan(0);
  });

  it("keeps an ordinary failure ordinary — no organization field appears", async () => {
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            title: "invalid_credentials",
            detail: "Email or password is incorrect.",
          }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);
    render(<LoginPage />);

    await userEvent.type(
      screen.getByLabelText("Email"),
      "owner@kilima.example",
    );
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/incorrect/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Organization")).not.toBeInTheDocument();
  });
});
