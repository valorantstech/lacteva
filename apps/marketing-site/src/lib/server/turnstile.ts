import "server-only";

/**
 * Cloudflare Turnstile, verified on the server (WO-103 · LACTEVA-AUTH-003).
 *
 * The two lead forms — Start free trial and Request a demo — have no secret
 * in them, which is exactly where bots go. With LACTEVA_TURNSTILE_SECRET_KEY
 * set (read at REQUEST time, like the leads webhook; never built in), every
 * submission must carry a token this asks Cloudflare about. Without the
 * secret the check is OFF and the forms work as before — the platform's
 * `turnstile` health probe is where that state is reported.
 *
 * Fails CLOSED: a verifier that cannot be reached has not said yes.
 */

export const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

/** Cloudflare's published test secrets behave offline as they do live. */
const TEST_SECRETS: Record<string, boolean> = {
  "1x0000000000000000000000000000000AA": true,
  "2x0000000000000000000000000000000AA": false,
  "3x0000000000000000000000000000000AA": false,
};

export function turnstileSecret(): string {
  return process.env.LACTEVA_TURNSTILE_SECRET_KEY ?? "";
}

export function turnstileEnabled(): boolean {
  return turnstileSecret() !== "";
}

export async function verifyTurnstile(
  token: string | undefined,
  remoteIp: string | null,
): Promise<boolean> {
  const secret = turnstileSecret();
  if (!secret) return true; // OFF — nothing to verify against
  if (!token) return false;
  if (secret in TEST_SECRETS) return TEST_SECRETS[secret];
  const form = new URLSearchParams({ secret, response: token });
  if (remoteIp) form.set("remoteip", remoteIp);
  try {
    const response = await fetch(SITEVERIFY_URL, { method: "POST", body: form });
    if (!response.ok) return false;
    const body = (await response.json()) as { success?: boolean };
    return body.success === true;
  } catch {
    return false;
  }
}

/** The caller's address as nginx forwards it; the first entry is the client. */
export function clientIp(request: Request): string | null {
  const forwarded = request.headers.get("x-forwarded-for");
  return forwarded ? forwarded.split(",")[0].trim() : null;
}
