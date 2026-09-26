/**
 * The lead forms' bot check is verified on the SERVER (WO-103). With no
 * secret the check is off; with Cloudflare's test secrets it answers as they
 * do without the network; with a real secret it asks siteverify and fails
 * closed on anything but an explicit yes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SITEVERIFY_URL, verifyTurnstile } from "@/lib/server/turnstile";

const ORIGINAL = process.env.LACTEVA_TURNSTILE_SECRET_KEY;

beforeEach(() => {
  delete process.env.LACTEVA_TURNSTILE_SECRET_KEY;
});
afterEach(() => {
  vi.unstubAllGlobals();
  if (ORIGINAL === undefined) delete process.env.LACTEVA_TURNSTILE_SECRET_KEY;
  else process.env.LACTEVA_TURNSTILE_SECRET_KEY = ORIGINAL;
});

describe("verifyTurnstile", () => {
  it("is OFF without a secret — any submission passes, token or not", async () => {
    expect(await verifyTurnstile(undefined, null)).toBe(true);
  });

  it("with a secret, no token is a refusal", async () => {
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "1x0000000000000000000000000000000AA";
    expect(await verifyTurnstile(undefined, null)).toBe(false);
    expect(await verifyTurnstile("", null)).toBe(false);
  });

  it("answers as Cloudflare's test secrets do, offline", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "1x0000000000000000000000000000000AA";
    expect(await verifyTurnstile("XXXX.DUMMY.TOKEN", null)).toBe(true);
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "2x0000000000000000000000000000000AA";
    expect(await verifyTurnstile("XXXX.DUMMY.TOKEN", null)).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("asks siteverify with the secret, the token and the caller's address, and believes only success", async () => {
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "0x4AAAAAAA-real-looking-secret";
    const seen: URLSearchParams[] = [];
    let answer: Response = new Response(JSON.stringify({ success: true }), { status: 200 });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        expect(url).toBe(SITEVERIFY_URL);
        seen.push(init?.body as URLSearchParams);
        return answer;
      }),
    );
    expect(await verifyTurnstile("XXXX.DUMMY.TOKEN", "203.0.113.9")).toBe(true);
    expect(seen[0].get("secret")).toBe("0x4AAAAAAA-real-looking-secret");
    expect(seen[0].get("response")).toBe("XXXX.DUMMY.TOKEN");
    expect(seen[0].get("remoteip")).toBe("203.0.113.9");
    answer = new Response(JSON.stringify({ success: false, "error-codes": ["invalid-input-response"] }), { status: 200 });
    expect(await verifyTurnstile("XXXX.DUMMY.TOKEN", null)).toBe(false);
    answer = new Response("busy", { status: 503 });
    expect(await verifyTurnstile("XXXX.DUMMY.TOKEN", null)).toBe(false);
  });

  it("fails closed when siteverify cannot be reached", async () => {
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "0x4AAAAAAA-real-looking-secret";
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network down"); }));
    expect(await verifyTurnstile("XXXX.DUMMY.TOKEN", null)).toBe(false);
  });
});
