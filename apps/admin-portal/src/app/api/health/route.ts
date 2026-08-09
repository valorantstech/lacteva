import { NextResponse } from "next/server";

/**
 * Portal liveness (PORTAL-001 / F-03).
 *
 * Answers for THIS process only. It deliberately does not call the platform:
 * a readiness check that fails when the backend is down would have Docker
 * restart a perfectly healthy portal during a database maintenance window,
 * and nginx would take it out of rotation for a fault it cannot fix.
 * The platform's own health is on the dashboard, where a human reads it.
 */
export function GET() {
  return NextResponse.json({ status: "ok", service: "admin-portal" });
}
