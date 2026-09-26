import { NextResponse } from "next/server";

/**
 * WO-103: the Turnstile SITE key for the lead forms, at request time. Public
 * by nature and read from the container's environment, not built into the
 * bundle — the same lesson as LACTEVA_SITE_URL (WO-76). Empty means the check
 * is off and the form renders no widget.
 */
export async function GET() {
  return NextResponse.json(
    { site_key: process.env.LACTEVA_TURNSTILE_SITE_KEY ?? "" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
