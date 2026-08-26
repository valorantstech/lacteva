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
import { ApiError, confirmPasswordReset, requestPasswordReset } from "@/lib/api";

/**
 * Reset a forgotten password (LACTEVA-ADMIN-003).
 *
 * Two steps, on one page: ask for a code, then spend it. The backend flow has
 * existed and been rate-limited and enumeration-safe for a long time; neither
 * login surface offered it, so a locked-out operator during a pilot was a
 * support call.
 *
 * **The enumeration rule is the whole design.** Step 1 says the SAME sentence
 * whatever happened — the platform answers 202 for an address it has never
 * seen and for one it has, and this page must not undo that by branching. So
 * there is no "no such account" state, no different heading, no different
 * next step: a person who mistypes their address gets the identical screen a
 * person who typed it correctly gets, and only their inbox can tell them
 * apart. Anything else turns this form into a way of asking "does this dairy
 * use Lacteva?".
 *
 * The one refusal worth showing is the rate limit, because "try again later"
 * is actionable and it says nothing about any account.
 *
 * Deliberately English (Decision D-1): a new, unwired surface. The LINK to it
 * lives on `/login`, which IS wired, and is keyed there.
 */
const MIN_PASSWORD = 10;

export default function ResetPasswordPage() {
  const [step, setStep] = useState<"request" | "confirm">("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** The same words for every outcome. See the enumeration note above. */
  const sent = `If an account exists for ${email}, a reset code has been sent.`;

  function refusal(err: unknown): string {
    if (err instanceof ApiError) {
      // The limiter is IP-based and says nothing about an account, so it is
      // safe — and necessary — to be honest about it.
      if (err.status === 429) return "Too many attempts — try again later.";
      return err.detail;
    }
    return "Could not reach the platform. Check your connection and try again.";
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestPasswordReset(email.trim());
      setStep("confirm");
    } catch (err) {
      // A 429 keeps the person on step 1; anything else that is not a rate
      // limit would be the platform failing, not the account being unknown.
      setError(refusal(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await confirmPasswordReset(code.trim(), password);
      // The notice is a KEY, not a sentence: the login page renders it from
      // its own catalog, so nothing this page writes can reach that screen.
      window.location.assign("/login?notice=reset");
    } catch (err) {
      setError(refusal(err));
      // The form keeps the code — retyping it because the password was short
      // is a small cruelty.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Reset your password</CardTitle>
          <CardDescription>
            {step === "request"
              ? "We will email you a one-time code."
              : sent}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {step === "request" ? (
            <form onSubmit={ask} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={busy}>
                {busy ? "Sending…" : "Send reset code"}
              </Button>
            </form>
          ) : (
            <form onSubmit={confirm} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="code">Reset code</Label>
                <Input
                  id="code"
                  required
                  autoComplete="off"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-password">New password</Label>
                <Input
                  id="new-password"
                  type="password"
                  required
                  minLength={MIN_PASSWORD}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  At least {MIN_PASSWORD} characters.
                </p>
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={busy}>
                {busy ? "Updating…" : "Set new password"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
