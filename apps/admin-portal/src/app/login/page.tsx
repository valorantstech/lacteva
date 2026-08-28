"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, login,
  describeError,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { LactevaLockup } from "@/components/lockup";

/**
 * Sign in (DEMO-010).
 *
 * This form used to ask for "Organization ID (tenant)" — a raw UUID, in a text
 * box, as the first thing anyone saw. Nobody knows their tenant UUID. It was
 * there because the platform resolved a login by (email, tenant), so a member
 * of an organization was invisible without it.
 *
 * The platform now resolves the organization from the credentials. The field
 * survives for exactly one case: an address whose password opens accounts in
 * MORE THAN ONE organization, which the platform answers with
 * `ambiguous_tenant` — and only after the password has verified. So the field
 * appears when it is needed and not before.
 */
/**
 * The notices this page is willing to show (LACTEVA-ADMIN-003).
 *
 * An ALLOWLIST, mapping a key to a catalog string — never the query string
 * itself. `?notice=` is attacker-controlled text on an unauthenticated page:
 * rendering it verbatim would let any link put arbitrary words above a
 * password box ("Your session expired — confirm your card details"), which is
 * a phishing surface handed out for free. An unknown key renders nothing.
 */
const NOTICES: Record<string, string> = { reset: "auth.notice.reset" };

export default function LoginPage() {
  const t = useT();
  // Read on the client, deliberately: this page is already a client component
  // and the value is cosmetic. `useSearchParams` would put the whole route
  // behind a Suspense boundary for one line of text.
  const noticeKey =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("notice")
      : null;
  const notice = noticeKey && NOTICES[noticeKey] ? t(NOTICES[noticeKey]) : null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [needsTenant, setNeedsTenant] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password, tenantId || undefined);
      // A FULL navigation, not `router.push` (DEMO-010).
      //
      // `AppShell` lives in the root layout and probes the session once, when
      // it mounts. A client-side push does not remount it, so it kept the
      // signed-out chrome it had established on this very page — and signing
      // in landed on a dashboard with NO NAVIGATION AT ALL until the user
      // happened to reload. Found in the browser; invisible to a test that
      // renders this page alone.
      //
      // Sign-out does not need this because it can call `setSession` on the
      // shell directly; a separate page cannot.
      window.location.assign("/");
    } catch (err) {
      if (err instanceof ApiError && err.title === "ambiguous_tenant") {
        setNeedsTenant(true);
        setError(err.detail);
      } else {
        setError(describeError(err, t("login.failed")));
      }
    } finally {
      setBusy(false);
    }
  }

  // Design System V1 (batch H): a plain div, and the classes are untouched.
  //  * `<main>` → `<div>` because the shell already renders the page's `main`
  //    landmark, so this was a second one — an accessibility fault, not a
  //    style preference.
  //  * `min-h-screen` STAYS. Everywhere else in this batch it was inherited
  //    padding doing nothing; here it is load-bearing, because it gives
  //    `items-center` a height to centre the sign-in card within. Removing it
  //    would push the card to the top of the page.
  return (
    // WO-39: the front door joins the brand.
    //
    // The soft dairy wash is the DS's own `--gradient-cream-fresh` — the
    // atmosphere language the rest of the product speaks — not a new colour.
    // `lacteva-settle` is the DS motion token for "something arrived", and
    // the global `prefers-reduced-motion` rule collapses it to 1ms, so a
    // person who asked not to be moved gets the finished page immediately
    // rather than a page that never finishes arriving.
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-[image:var(--gradient-cream-fresh)] p-8">
      {/*
        The full lockup — the can, the owner's TRACED letterforms and the
        tagline — from the one generated composition the shell also wears.
        What stood here was the retired BRAND-003 lit drop with "Lacteva" set
        in the UI font: two brand generations behind the shell around it, and
        the first thing a customer sees at the real URL.
      */}
      <LactevaLockup withTagline idPrefix="login" className="lacteva-settle" />
      <Card className="lacteva-settle w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t("login.title")}</CardTitle>
          <CardDescription>{t("login.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          {notice && (
            <p className="mb-4 text-sm text-muted-foreground" role="status">
              {notice}
            </p>
          )}
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">{t("auth.email")}</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">{t("auth.password")}</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {needsTenant ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="tenant">{t("auth.organization")}</Label>
                <Input
                  id="tenant"
                  placeholder={t("login.orgIdPlaceholder")}
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {t("login.multiOrgHelp")}
                </p>
              </div>
            ) : null}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy}>
              {busy ? t("auth.signingIn") : t("auth.signIn")}
            </Button>
            {/* Quiet, under the form: a way out for somebody locked out,
                without competing with the thing everybody else came to do. */}
            <a
              href="/reset-password"
              className="text-center text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
            >
              {t("auth.forgotPassword")}
            </a>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
