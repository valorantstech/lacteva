/**
 * The sign-up form, and the wording it shares with the reset form (WO-103).
 *
 * The owner: "once click we have 3 fields, code, name and password. add
 * retype password as well along with captcha or something." So: Confirm
 * password, refused client-side with a clear sentence when the two differ
 * (nothing is sent), a Show/Hide toggle on both fields, and — when the portal
 * has a Turnstile site key — the widget's token in the request body, named as
 * the platform expects it.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AcceptInvitationPage from "@/app/accept-invitation/page";
import ResetPasswordPage from "@/app/reset-password/page";
import LoginPage from "@/app/login/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

type Options = Parameters<NonNullable<Window["turnstile"]>["render"]>[1];

/** QA-005: never THE alert — the one that says this. */
async function alertSaying(pattern: RegExp, container: HTMLElement = document.body) {
  return waitFor(() => {
    const found = within(container)
      .getAllByRole("alert")
      .find((el) => pattern.test(el.textContent ?? ""));
    if (!found) throw new Error(`no alert yet matching ${pattern}`);
    return found;
  });
}


/** Every request the pages make; `siteKey` is what `/api/auth/turnstile` says. */
function stubFetch(siteKey: string) {
  const calls: { url: string; body: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/auth/turnstile") return json({ site_key: siteKey });
      if (url.includes("/api/auth/session")) return json({ authenticated: false });
      calls.push({ url, body: String(init?.body ?? "") });
      if (url === "/api/auth/login") return new Response(null, { status: 204 });
      if (url === "/api/auth/password-reset/request") return json({ status: "accepted" }, 202);
      return json({ id: "u9" }, 201);
    }),
  );
  return calls;
}

function fakeTurnstile() {
  const rendered: Options[] = [];
  window.turnstile = {
    render: vi.fn((_el: HTMLElement, options: Options) => {
      rendered.push(options);
      // The challenge passes at once, as the invisible widget usually does.
      setTimeout(() => options.callback("XXXX.DUMMY.TOKEN"), 0);
      return `widget-${rendered.length}`;
    }),
    remove: vi.fn(),
    reset: vi.fn(),
  };
  return rendered;
}

beforeEach(() => {
  vi.stubGlobal("location", { assign: vi.fn(), pathname: "/accept-invitation", search: "", hash: "" });
  vi.stubGlobal("history", { replaceState: vi.fn() });
});
afterEach(() => {
  delete window.turnstile;
  vi.unstubAllGlobals();
});

describe("Confirm password", () => {
  it("refuses a mismatch before anything is sent, and says so plainly", async () => {
    const calls = stubFetch("");
    render(<AcceptInvitationPage />);
    await userEvent.type(screen.getByLabelText("Invitation code"), "code-abc");
    await userEvent.type(screen.getByLabelText("Full name"), "Sarwari Patel");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.type(screen.getByLabelText("Confirm password"), "correct-horse-batery");
    expect(await alertSaying(/The two passwords do not match\./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Join" }));
    expect(calls).toEqual([]);
    expect(screen.getByText(/Type the same password in both fields/)).toBeInTheDocument();
    // Fix the second field and it goes through, with the body the platform
    // has always received — no token key when there is no site key.
    await userEvent.clear(screen.getByLabelText("Confirm password"));
    await userEvent.type(screen.getByLabelText("Confirm password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Join" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(JSON.parse(calls[0].body)).toEqual({
      token: "code-abc",
      full_name: "Sarwari Patel",
      password: "correct-horse-battery",
    });
  });

  it("lets people see what they typed, on both fields", async () => {
    stubFetch("");
    render(<AcceptInvitationPage />);
    const password = screen.getByLabelText("Password");
    const confirm = screen.getByLabelText("Confirm password");
    expect(password).toHaveAttribute("type", "password");
    const toggles = screen.getAllByRole("button", { name: "Show" });
    expect(toggles).toHaveLength(2);
    await userEvent.click(toggles[0]);
    expect(password).toHaveAttribute("type", "text");
    expect(confirm).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Hide" })).toHaveAttribute("aria-pressed", "true");
  });

  it("guards the reset form the same way", async () => {
    const calls = stubFetch("");
    vi.stubGlobal("location", { assign: vi.fn(), pathname: "/reset-password", search: "", hash: "#code=code-xyz" });
    render(<ResetPasswordPage />);
    await screen.findByLabelText("Reset code");
    await userEvent.type(screen.getByLabelText("New password"), "correct-horse-battery");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different-password-1");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(calls).toEqual([]);
    expect(screen.getByText(/Type the same password in both fields/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Show" })).toHaveLength(2);
  });
});

describe("the Turnstile token", () => {
  it("rides in the sign-up body when the portal has a site key", async () => {
    const calls = stubFetch("1x00000000000000000000AA");
    const rendered = fakeTurnstile();
    render(<AcceptInvitationPage />);
    await waitFor(() => expect(rendered).toHaveLength(1));
    expect(rendered[0].sitekey).toBe("1x00000000000000000000AA");
    await userEvent.type(screen.getByLabelText("Invitation code"), "code-abc");
    await userEvent.type(screen.getByLabelText("Full name"), "Sarwari Patel");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.type(screen.getByLabelText("Confirm password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Join" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(JSON.parse(calls[0].body).turnstile_token).toBe("XXXX.DUMMY.TOKEN");
  });

  it("rides in the forgot-password request", async () => {
    const calls = stubFetch("1x00000000000000000000AA");
    const rendered = fakeTurnstile();
    vi.stubGlobal("location", { assign: vi.fn(), pathname: "/reset-password", search: "", hash: "" });
    render(<ResetPasswordPage />);
    await waitFor(() => expect(rendered).toHaveLength(1));
    await userEvent.type(screen.getByLabelText("Email"), "sarwari@patel.example");
    await userEvent.click(screen.getByRole("button", { name: "Send reset code" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toBe("/api/auth/password-reset/request");
    expect(JSON.parse(calls[0].body)).toEqual({
      email: "sarwari@patel.example",
      turnstile_token: "XXXX.DUMMY.TOKEN",
    });
  });

  it("rides in the sign-in, for the platform to ask for after repeated failures", async () => {
    const calls = stubFetch("1x00000000000000000000AA");
    const rendered = fakeTurnstile();
    vi.stubGlobal("location", { assign: vi.fn(), pathname: "/login", search: "", hash: "" });
    render(<LoginPage />);
    await waitFor(() => expect(rendered).toHaveLength(1));
    await userEvent.type(screen.getByLabelText("Email"), "sarwari@patel.example");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toBe("/api/auth/login");
    expect(JSON.parse(calls[0].body).turnstile_token).toBe("XXXX.DUMMY.TOKEN");
  });

  it("is absent — key and all — when the portal has no site key", async () => {
    const calls = stubFetch("");
    vi.stubGlobal("location", { assign: vi.fn(), pathname: "/login", search: "", hash: "" });
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "sarwari@patel.example");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(JSON.parse(calls[0].body)).toEqual({
      email: "sarwari@patel.example",
      password: "correct-horse-battery",
    });
    expect(screen.queryByTestId("turnstile")).toBeNull();
  });
});
