/**
 * Forgotten password, portal side (LACTEVA-ADMIN-003).
 *
 * The backend flow has been rate-limited and enumeration-safe since before
 * either client shipped; neither login surface offered it, so a locked-out
 * operator during a pilot was a support call.
 *
 * What is defended here is the part a UI can quietly undo:
 *
 *   1. **enumeration.** The platform answers 202 for an address it has never
 *      seen exactly as for one it knows. A page that branched on the outcome —
 *      a different heading, a different next step, a "no such account" — would
 *      hand back the answer the 202 exists to withhold, and would do it
 *      without touching the backend at all. So the test asks for a real
 *      address and a fictional one and demands the screens be INDISTINGUISHABLE;
 *   2. **the notice allowlist.** `/login?notice=` is attacker-controlled text
 *      on an unauthenticated page. Rendering it verbatim would let any link
 *      put arbitrary words above a password box. Known key → catalog string;
 *      anything else → nothing at all.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const assign = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/reset-password",
}));

// jsdom's `window.location` is not assignable; replace it, keeping a `search`
// the login page can read.
function atUrl(search: string) {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, search, assign },
  });
}

import LoginPage from "@/app/login/page";
import ResetPasswordPage from "@/app/reset-password/page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  assign.mockClear();
  vi.unstubAllGlobals();
  atUrl("");
});

/** Step 1, for whatever address, against whatever the platform answers. */
async function askFor(email: string, response: Response) {
  const spy = vi.fn(async () => response);
  vi.stubGlobal("fetch", spy);
  render(<ResetPasswordPage />);
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.click(
    screen.getByRole("button", { name: "Send reset code" }),
  );
  return spy;
}

describe("asking for a reset code", () => {
  it("sends the request to the PRE-AUTH route, never the session proxy", async () => {
    let seenUrl = "";
    let seenBody = "";
    const spy = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      seenUrl = String(url);
      seenBody = String(init?.body ?? "");
      return json({ status: "accepted" }, 202);
    });
    vi.stubGlobal("fetch", spy);

    render(<ResetPasswordPage />);
    await userEvent.type(
      screen.getByLabelText("Email"),
      "manager@kilima.example",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send reset code" }),
    );

    await waitFor(() => expect(spy).toHaveBeenCalled());
    // /api/proxy would refuse this: a locked-out person has no session.
    expect(seenUrl).toBe("/api/auth/password-reset/request");
    expect(seenUrl).not.toContain("/api/proxy");
    expect(JSON.parse(seenBody)).toEqual({ email: "manager@kilima.example" });
  });

  it("says the SAME thing for an account that exists and one that does not", async () => {
    // The platform answers 202 both times — that is the whole defence, and a
    // UI is the easiest place to lose it.
    await askFor("manager@kilima.example", json({ status: "accepted" }, 202));
    await screen.findByLabelText("Reset code");
    const real = document.body.textContent!.replace(
      "manager@kilima.example",
      "{email}",
    );
    document.body.innerHTML = "";

    await askFor("nobody@nowhere.example", json({ status: "accepted" }, 202));
    await screen.findByLabelText("Reset code");
    const fictional = document.body.textContent!.replace(
      "nobody@nowhere.example",
      "{email}",
    );

    // Identical down to the character, once the address itself is normalised.
    expect(fictional).toBe(real);
    expect(real).toContain("If an account exists for {email}");
  });

  it("is honest about a rate limit, and stays on step 1", async () => {
    await askFor(
      "manager@kilima.example",
      json(
        { title: "rate_limited", status: 429, detail: "slow down" },
        429,
      ),
    );

    await waitFor(() =>
      expect(
        screen.getByText("Too many attempts — try again later."),
      ).toBeTruthy(),
    );
    // A 429 is about the IP, not the account: it reveals nothing, and the
    // person needs to know the request did NOT go through.
    expect(screen.queryByLabelText("Reset code")).toBeNull();
  });
});

describe("setting the new password", () => {
  async function reachStepTwo() {
    const spy = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).endsWith("/request")) {
        return json({ status: "accepted" }, 202);
      }
      calls.push([String(url), String(init?.body ?? "")]);
      return next;
    });
    vi.stubGlobal("fetch", spy);
    render(<ResetPasswordPage />);
    await userEvent.type(
      screen.getByLabelText("Email"),
      "manager@kilima.example",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send reset code" }),
    );
    await screen.findByLabelText("Reset code");
    return spy;
  }
  let calls: [string, string][] = [];
  let next: Response;

  beforeEach(() => {
    calls = [];
    next = new Response(null, { status: 204 });
  });

  it("spends the code and returns to sign-in with an allowlisted notice", async () => {
    await reachStepTwo();

    await userEvent.type(screen.getByLabelText("Reset code"), "code-xyz");
    await userEvent.type(
      screen.getByLabelText("New password"),
      "correct-horse-battery",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Set new password" }),
    );

    await waitFor(() => expect(calls.length).toBe(1));
    const [url, body] = calls[0];
    expect(url).toBe("/api/auth/password-reset/confirm");
    // The code travels in the BODY. A reset code in a query string reaches
    // browser history, referrers and every access log on the way.
    expect(JSON.parse(body)).toEqual({
      token: "code-xyz",
      new_password: "correct-horse-battery",
    });
    // A KEY, never a sentence: nothing this page writes reaches that screen.
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/login?notice=reset"),
    );
  });

  it("shows the platform's reason for a spent code and keeps the code", async () => {
    next = new Response(
      JSON.stringify({
        title: "invalid_token",
        status: 400,
        detail: "That reset code has expired.",
      }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
    await reachStepTwo();

    await userEvent.type(screen.getByLabelText("Reset code"), "stale-code");
    await userEvent.type(
      screen.getByLabelText("New password"),
      "correct-horse-battery",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Set new password" }),
    );

    await waitFor(() =>
      expect(screen.getByText("That reset code has expired.")).toBeTruthy(),
    );
    expect(
      (screen.getByLabelText("Reset code") as HTMLInputElement).value,
    ).toBe("stale-code");
    expect(assign).not.toHaveBeenCalled();
  });
});

describe("the login notice", () => {
  it("offers a quiet way through for somebody locked out", () => {
    render(<LoginPage />);
    const link = screen.getByRole("link", { name: "Forgot password?" });
    expect(link.getAttribute("href")).toBe("/reset-password");
  });

  it("renders the catalog string for an allowlisted key", () => {
    atUrl("?notice=reset");
    render(<LoginPage />);
    expect(
      screen.getByText("Your password was updated — sign in to continue."),
    ).toBeTruthy();
  });

  it("renders NOTHING for a key it does not know", () => {
    // The phishing case: any link could otherwise put words above a password
    // box. Both an unknown key and raw text must vanish.
    atUrl("?notice=Your%20session%20expired%20%E2%80%94%20confirm%20your%20card");
    render(<LoginPage />);
    expect(screen.queryByText(/confirm your card/)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("renders nothing when there is no notice at all", () => {
    atUrl("");
    render(<LoginPage />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
