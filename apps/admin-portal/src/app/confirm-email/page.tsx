"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
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
import { LactevaLockup } from "@/components/lockup";
import { ApiError, confirmEmailChange } from "@/lib/api";

/**
 * The new address confirms an email change (WO-87 §3).
 *
 * The person arrives from the message the NEW address received, holding a
 * one-time code and possibly no session at all. On success the platform has
 * moved their login and revoked every session they held, so the only honest
 * next step is the login page — with the new address.
 *
 * Deliberately English (Decision D-1): a new, unwired surface, like
 * `/reset-password`.
 */
export default function ConfirmEmailPage() {
  return (
    <Suspense fallback={null}>
      <ConfirmEmail />
    </Suspense>
  );
}

function ConfirmEmail() {
  const params = useSearchParams();
  const [code, setCode] = useState(params.get("token") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  function refusal(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.status === 429) return "Too many attempts — try again later.";
      if (err.status === 400)
        return "That code is not valid any more — it may have expired, been cancelled, or already been used. Ask for the change again.";
      return err.detail;
    }
    return "Could not reach the platform. Check your connection and try again.";
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await confirmEmailChange(code.trim());
      setDone(true);
    } catch (err) {
      setError(refusal(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-[image:var(--gradient-cream-fresh)] p-8">
      <LactevaLockup withTagline idPrefix="confirm-email" className="lacteva-settle" />
      <Card className="lacteva-settle w-full max-w-sm">
        <CardHeader>
          <CardTitle>Confirm your new email</CardTitle>
          <CardDescription>
            {done
              ? "Done. This address is now your login. Every earlier session was signed out — sign in again with the new address."
              : "Use the code that was sent to the new address. Until you do, nothing about your account changes and the old address keeps working."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {done ? (
            <Button
              type="button"
              onClick={() => window.location.assign("/login")}
              data-testid="confirm-email-login"
            >
              Go to sign in
            </Button>
          ) : (
            <form onSubmit={confirm} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="code">Confirmation code</Label>
                <Input
                  id="code"
                  required
                  autoComplete="off"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </div>
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}
              <Button type="submit" disabled={busy || !code.trim()}>
                {busy ? "Confirming…" : "Confirm"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
