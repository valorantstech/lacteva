import { NextResponse } from "next/server";

/**
 * WO-103: the Turnstile SITE key, at request time. Public by nature — it is
 * in the page for every visitor — and read here from the container's
 * environment rather than built into the bundle, so one image serves every
 * deployment and turning the check on is a configuration change, not a
 * rebuild. Empty means off, and the API's `turnstile` health probe says so.
 */
export async function GET() {
  return NextResponse.json(
    { site_key: process.env.LACTEVA_TURNSTILE_SITE_KEY ?? "" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
