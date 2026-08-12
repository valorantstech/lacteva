"use client";

import { useRouter } from "next/navigation";
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
  const router = useRouter();
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
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError && err.title === "ambiguous_tenant") {
        setNeedsTenant(true);
        setError(err.detail);
      } else {
        setError(err instanceof ApiError ? err.detail : "Login failed");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in to Lacteva</CardTitle>
          <CardDescription>Sign in with your email and password.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
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
                <Label htmlFor="tenant">Organization</Label>
                <Input
                  id="tenant"
                  placeholder="organization id"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  This sign-in works for more than one organization. Paste the id of the one you
                  want.
                </p>
              </div>
            ) : null}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
