/**
 * The lead forms are verified on the server (WO-103): with a Turnstile
 * secret set, a submission without a valid token is refused before it
 * reaches the leads webhook; with none, the forms work exactly as before.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { POST } from "@/app/api/demo-request/route";

const LEAD = {
  name: "Sarwari Patel",
  email: "sarwari@patel.example",
  organization: "Patel Dairy Shop and Sweets",
  country: "India",
  intent: "trial",
};

function post(body: unknown, headers: Record<string, string> = {}) {
  return POST(
    new Request("http://marketing.test/api/demo-request", {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
    }),
  );
}

const saved = { ...process.env };
beforeEach(() => {
  process.env.LACTEVA_LEADS_WEBHOOK_URL = "https://leads.example/hook";
  delete process.env.LACTEVA_TURNSTILE_SECRET_KEY;
});
afterEach(() => {
  vi.unstubAllGlobals();
  process.env.LACTEVA_LEADS_WEBHOOK_URL = saved.LACTEVA_LEADS_WEBHOOK_URL;
  if (saved.LACTEVA_TURNSTILE_SECRET_KEY === undefined) delete process.env.LACTEVA_TURNSTILE_SECRET_KEY;
  else process.env.LACTEVA_TURNSTILE_SECRET_KEY = saved.LACTEVA_TURNSTILE_SECRET_KEY;
});

describe("POST /api/demo-request", () => {
  it("with no secret, forwards the lead as before — no token asked for", async () => {
    const webhook = vi.fn(async () => new Response("ok", { status: 200 }));
    vi.stubGlobal("fetch", webhook);
    const response = await post(LEAD);
    expect(response.status).toBe(202);
    expect(webhook).toHaveBeenCalledTimes(1);
  });

  it("with a secret, refuses a submission without a token before the webhook sees it", async () => {
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "1x0000000000000000000000000000000AA";
    const webhook = vi.fn(async () => new Response("ok", { status: 200 }));
    vi.stubGlobal("fetch", webhook);
    const response = await post(LEAD);
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ code: "captcha_required" });
    expect(webhook).not.toHaveBeenCalled();
  });

  it("with a secret and a token Cloudflare vouches for, forwards the lead", async () => {
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "1x0000000000000000000000000000000AA";
    const webhook = vi.fn(async () => new Response("ok", { status: 200 }));
    vi.stubGlobal("fetch", webhook);
    const response = await post({ ...LEAD, turnstileToken: "XXXX.DUMMY.TOKEN" });
    expect(response.status).toBe(202);
    expect(webhook).toHaveBeenCalledTimes(1);
  });

  it("with a secret and a token Cloudflare rejects, refuses", async () => {
    process.env.LACTEVA_TURNSTILE_SECRET_KEY = "2x0000000000000000000000000000000AA";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("ok", { status: 200 })));
    const response = await post({ ...LEAD, turnstileToken: "XXXX.DUMMY.TOKEN" });
    expect(response.status).toBe(400);
  });
});
