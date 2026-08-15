import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";

function jsonRequest(body: unknown): Request {
  return new Request("http://localhost/api/demo-request", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

const VALID = {
  name: "Amina",
  email: "amina@example.coop",
  organization: "Example Dairy Cooperative",
  country: "Kenya",
  dailyVolume: "2,000 – 20,000 L/day",
  message: "",
};

describe("POST /api/demo-request", () => {
  afterEach(() => {
    delete process.env.LACTEVA_LEADS_WEBHOOK_URL;
  });

  it("rejects a non-JSON body", async () => {
    const response = await POST(jsonRequest("not json"));
    expect(response.status).toBe(400);
  });

  it("rejects a missing required field", async () => {
    const response = await POST(jsonRequest({ ...VALID, organization: " " }));
    expect(response.status).toBe(422);
    expect((await response.json()).code).toBe("missing_field");
  });

  it("rejects an invalid email", async () => {
    const response = await POST(jsonRequest({ ...VALID, email: "not-an-email" }));
    expect(response.status).toBe(422);
    expect((await response.json()).code).toBe("invalid_email");
  });

  it("answers 503 when no webhook is configured — the guard can refuse", async () => {
    const response = await POST(jsonRequest(VALID));
    expect(response.status).toBe(503);
    expect((await response.json()).code).toBe("not_recorded");
  });

  it("forwards a valid request and answers 202", async () => {
    process.env.LACTEVA_LEADS_WEBHOOK_URL = "https://crm.example/hook";
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 200 }));
    const response = await POST(jsonRequest(VALID));
    expect(response.status).toBe(202);
    expect(fetchSpy).toHaveBeenCalledWith(
      "https://crm.example/hook",
      expect.objectContaining({ method: "POST" }),
    );
    const forwarded = JSON.parse(
      (fetchSpy.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(forwarded.source).toBe("marketing-site");
    expect(forwarded.email).toBe(VALID.email);
  });

  it("forwards trial intent, phone, and organization type", async () => {
    process.env.LACTEVA_LEADS_WEBHOOK_URL = "https://crm.example/hook";
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 200 }));
    const response = await POST(
      jsonRequest({
        ...VALID,
        intent: "trial",
        phone: "+254 700 000000",
        organizationType: "Cooperative",
      }),
    );
    expect(response.status).toBe(202);
    const forwarded = JSON.parse(
      (fetchSpy.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(forwarded.intent).toBe("trial");
    expect(forwarded.phone).toBe("+254 700 000000");
    expect(forwarded.organizationType).toBe("Cooperative");
  });

  it("answers 502 when the webhook fails, without leaking the reason", async () => {
    process.env.LACTEVA_LEADS_WEBHOOK_URL = "https://crm.example/hook";
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 500 }),
    );
    const response = await POST(jsonRequest(VALID));
    expect(response.status).toBe(502);
    const problem = await response.json();
    expect(JSON.stringify(problem)).not.toContain("crm.example");
  });
});
