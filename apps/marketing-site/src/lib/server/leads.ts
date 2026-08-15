import "server-only";

/**
 * Demo-request forwarding.
 *
 * The platform has no public lead endpoint (nothing unauthenticated in
 * platform-core besides auth and JWKS), so the site forwards submissions to
 * an operator-configured webhook — a CRM or form relay. Same discipline as
 * the admin portal's backend.ts: the URL is read from the environment at
 * REQUEST time, never baked into the image, never sent to a browser.
 */

export type DemoRequest = {
  /** "demo" (book a demo) or "trial" (30-day free trial request). */
  intent: string;
  name: string;
  email: string;
  organization: string;
  country: string;
  phone: string;
  organizationType: string;
  dailyVolume: string;
  message: string;
};

export class LeadsNotConfiguredError extends Error {
  constructor() {
    super("LACTEVA_LEADS_WEBHOOK_URL is not set");
    this.name = "LeadsNotConfiguredError";
  }
}

export async function forwardDemoRequest(request: DemoRequest): Promise<void> {
  const url = process.env.LACTEVA_LEADS_WEBHOOK_URL;
  if (!url) {
    throw new LeadsNotConfiguredError();
  }
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source: "marketing-site", ...request }),
  });
  if (!response.ok) {
    throw new Error(`Lead webhook answered ${response.status}`);
  }
}
