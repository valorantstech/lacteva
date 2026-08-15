import { NextResponse } from "next/server";

/**
 * Site liveness, same contract as the admin portal's: answers for THIS
 * process only, used by the container healthcheck.
 */
export function GET() {
  return NextResponse.json({ status: "ok", service: "marketing-site" });
}
