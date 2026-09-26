/**
 * One-time codes on the pre-auth pages (WO-100).
 *
 * The email carries the code in the URL FRAGMENT — `/accept-invitation#code=…`
 * — because a fragment is never sent to the server: it reaches no access
 * log, no proxy log, no log pipeline, which is what SEC-003 / F-04 requires
 * of a token that travels only by email. The page reads it once, prefills
 * the code, and removes it from the address bar so it does not sit in
 * browser history either.
 *
 * And a code pasted by hand is forgiven its surroundings: the first real
 * customer's owner long-pressed the code on a phone and got the full stop
 * after it. The token is the longest run of the token alphabet; everything
 * else — quotes, "code:", line breaks — is dropped. The server does the same.
 */

/** The alphabet `secrets.token_urlsafe` draws from. */
const TOKEN_RUN = /[A-Za-z0-9_-]+/g;

export function normaliseCode(raw: string): string {
  const runs = raw.match(TOKEN_RUN) ?? [];
  return runs.reduce((best, run) => (run.length > best.length ? run : best), "");
}

/**
 * The code carried in the fragment, if any — read once, then removed from
 * the address bar. Returns "" when there is none.
 */
export function takeCodeFromFragment(): string {
  if (typeof window === "undefined") return "";
  const hash = window.location.hash;
  const match = /[#&]code=([^&]+)/.exec(hash);
  if (!match) return "";
  const code = normaliseCode(decodeURIComponent(match[1]));
  try {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  } catch {
    // A browser that refuses is still one that never sent the fragment anywhere.
  }
  return code;
}
