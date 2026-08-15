import { NextResponse } from "next/server";
import {
  forwardDemoRequest,
  LeadsNotConfiguredError,
  type DemoRequest,
} from "@/lib/server/leads";

const REQUIRED_FIELDS = ["name", "email", "organization", "country"] as const;
const MAX_FIELD_LENGTH = 2000;

/**
 * Public demo-request intake. Validates shape, then forwards server-side.
 * Errors follow the platform's problem-shaped convention: a stable machine
 * `code` plus a human `detail`, and no internal information in either.
 */
export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { code: "invalid_json", detail: "The request body must be JSON." },
      { status: 400 },
    );
  }

  for (const field of REQUIRED_FIELDS) {
    const value = body[field];
    if (typeof value !== "string" || value.trim() === "") {
      return NextResponse.json(
        { code: "missing_field", detail: `"${field}" is required.` },
        { status: 422 },
      );
    }
  }
  for (const [field, value] of Object.entries(body)) {
    if (typeof value === "string" && value.length > MAX_FIELD_LENGTH) {
      return NextResponse.json(
        { code: "field_too_long", detail: `"${field}" is too long.` },
        { status: 422 },
      );
    }
  }
  const email = String(body.email);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json(
      { code: "invalid_email", detail: "Enter a valid email address." },
      { status: 422 },
    );
  }

  const demoRequest: DemoRequest = {
    intent: body.intent === "trial" ? "trial" : "demo",
    name: String(body.name).trim(),
    email: email.trim(),
    organization: String(body.organization).trim(),
    country: String(body.country).trim(),
    phone: typeof body.phone === "string" ? body.phone.trim() : "",
    organizationType:
      typeof body.organizationType === "string" ? body.organizationType.trim() : "",
    dailyVolume: typeof body.dailyVolume === "string" ? body.dailyVolume.trim() : "",
    message: typeof body.message === "string" ? body.message.trim() : "",
  };

  try {
    await forwardDemoRequest(demoRequest);
  } catch (error) {
    const status = error instanceof LeadsNotConfiguredError ? 503 : 502;
    return NextResponse.json(
      {
        code: "not_recorded",
        detail:
          "We could not record your request right now. Please try again later.",
      },
      { status },
    );
  }
  return NextResponse.json({ status: "received" }, { status: 202 });
}
