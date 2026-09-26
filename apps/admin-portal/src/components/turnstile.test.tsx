/**
 * The browser half of Turnstile (WO-103). What is pinned: the widget renders
 * only with a site key, it asks Cloudflare's script for a widget with THAT
 * key, the token it produces reaches the form, and an expired challenge takes
 * the token back — so a form never sends a stale one.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Turnstile, useTurnstileSiteKey } from "@/components/turnstile";

type Options = Parameters<NonNullable<Window["turnstile"]>["render"]>[1];

function fakeTurnstile() {
  const calls: Options[] = [];
  const api = {
    render: vi.fn((_el: HTMLElement, options: Options) => {
      calls.push(options);
      return `widget-${calls.length}`;
    }),
    remove: vi.fn(),
    reset: vi.fn(),
  };
  window.turnstile = api;
  return { api, calls };
}

afterEach(() => {
  delete window.turnstile;
  vi.unstubAllGlobals();
});

describe("the Turnstile widget", () => {
  it("renders nothing without a site key", () => {
    const { container } = render(<Turnstile siteKey="" onToken={() => {}} />);
    expect(container.innerHTML).toBe("");
  });

  it("asks Cloudflare for a widget with the site key, and hands the token to the form", async () => {
    const { api, calls } = fakeTurnstile();
    const onToken = vi.fn();
    render(<Turnstile siteKey="1x00000000000000000000AA" onToken={onToken} />);
    await waitFor(() => expect(api.render).toHaveBeenCalledTimes(1));
    expect(calls[0].sitekey).toBe("1x00000000000000000000AA");
    expect(screen.getByTestId("turnstile")).toBeInTheDocument();
    act(() => calls[0].callback("XXXX.DUMMY.TOKEN"));
    expect(onToken).toHaveBeenLastCalledWith("XXXX.DUMMY.TOKEN");
    // Expiry takes it back — the form must not send a token Cloudflare no
    // longer vouches for.
    act(() => calls[0]["expired-callback"]?.());
    expect(onToken).toHaveBeenLastCalledWith(null);
  });

  it("removes its widget when the form goes away", async () => {
    const { api } = fakeTurnstile();
    const { unmount } = render(<Turnstile siteKey="1x00000000000000000000AA" onToken={() => {}} />);
    await waitFor(() => expect(api.render).toHaveBeenCalled());
    unmount();
    expect(api.remove).toHaveBeenCalledWith("widget-1");
  });
});

describe("the site key", () => {
  function Probe() {
    const key = useTurnstileSiteKey();
    return <span data-testid="key">{key === null ? "pending" : key === "" ? "off" : key}</span>;
  }

  it("comes from the portal's runtime configuration, not the bundle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        expect(String(input)).toBe("/api/auth/turnstile");
        return new Response(JSON.stringify({ site_key: "1x00000000000000000000AA" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    render(<Probe />);
    expect(await screen.findByText("1x00000000000000000000AA")).toBeInTheDocument();
  });

  it("is OFF when the route answers nothing usable — never a guess", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 404 })));
    render(<Probe />);
    expect(await screen.findByText("off")).toBeInTheDocument();
  });
});
