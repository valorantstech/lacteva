/**
 * PORTAL-001 / F-09 — the flow every other page depends on.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

import LoginPage from "@/app/login/page";

beforeEach(() => {
  push.mockClear();
  vi.unstubAllGlobals();
});

async function fillIn(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Email"), "manager@kilima.example");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
}

describe("login page", () => {
  it("signs in and moves on", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/centers"));
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/auth/login");
  });

  it("shows the platform's reason when the credentials are wrong, and stays put", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Email or password is incorrect." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Email or password is incorrect.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("tells the operator they are rate limited rather than that the password is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Too many requests. Please wait and try again." }), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/Too many requests/)).toBeInTheDocument();
  });

  it("never writes a credential into browser storage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const user = userEvent.setup();

    render(<LoginPage />);
    await fillIn(user);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
