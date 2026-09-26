"use client";

/**
 * Cloudflare Turnstile, the browser half (WO-103 · LACTEVA-AUTH-003).
 *
 * The widget is decoration: what counts is the API verifying the token it
 * produces against Cloudflare on every protected request (`core/turnstile.py`).
 * This component's only job is to produce that token and hand it to the form,
 * and to stay out of the way — Turnstile is usually invisible, so most people
 * never see anything here at all.
 *
 * The SITE KEY is read at RUNTIME from `/api/auth/turnstile`, never built into
 * the bundle (WO-76's lesson: a build-time address was forgotten for three
 * weeks). No key → no widget → the form sends no token, and the platform,
 * having no secret either, does not ask for one. The two halves are switched
 * on by the same pair of keys, so they cannot disagree.
 */

import { useEffect, useRef, useState } from "react";

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type TurnstileApi = {
  render: (
    container: HTMLElement,
    options: {
      sitekey: string;
      callback: (token: string) => void;
      "expired-callback"?: () => void;
      "error-callback"?: () => void;
      theme?: "light" | "dark" | "auto";
      size?: "normal" | "flexible" | "compact";
    },
  ) => string;
  remove: (widgetId: string) => void;
  reset: (widgetId: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let scriptPromise: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => {
        scriptPromise = null;
        reject(new Error("turnstile script failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

/** The site key, from the portal's own runtime configuration. `""` means the
 *  check is off; `null` means not known yet. */
export function useTurnstileSiteKey(): string | null {
  const [siteKey, setSiteKey] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/turnstile", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { site_key: "" }))
      .then((body: { site_key?: string }) => {
        if (!cancelled) setSiteKey(body.site_key ?? "");
      })
      .catch(() => !cancelled && setSiteKey(""));
    return () => {
      cancelled = true;
    };
  }, []);
  return siteKey;
}

export function Turnstile({
  siteKey,
  onToken,
}: {
  siteKey: string;
  /** Called with the token when the challenge passes, and with `null` when it
   *  expires or errors, so the form never sends a stale one. */
  onToken: (token: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  // The latest callback, read from inside the widget's own callbacks — kept
  // in a ref (written in an effect, never during render) so re-rendering the
  // form does not re-render the widget.
  const onTokenRef = useRef(onToken);
  useEffect(() => {
    onTokenRef.current = onToken;
  }, [onToken]);

  useEffect(() => {
    const element = container.current;
    if (!siteKey || !element) return;
    let widgetId: string | null = null;
    let cancelled = false;
    loadScript()
      .then(() => {
        if (cancelled || !window.turnstile) return;
        widgetId = window.turnstile.render(element, {
          sitekey: siteKey,
          size: "flexible",
          callback: (token) => onTokenRef.current(token),
          "expired-callback": () => onTokenRef.current(null),
          "error-callback": () => onTokenRef.current(null),
        });
      })
      .catch(() => onTokenRef.current(null));
    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [siteKey]);

  if (!siteKey) return null;
  return <div ref={container} data-testid="turnstile" className="min-h-[65px]" />;
}
