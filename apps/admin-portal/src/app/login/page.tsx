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
import { ApiError, login } from "@/lib/api";
import { useT } from "@/lib/i18n";

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
export default function LoginPage() {
  const t = useT();
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
        setError(err instanceof ApiError ? err.detail : t("login.failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t("login.title")}</CardTitle>
          <CardDescription>{t("login.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
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
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
