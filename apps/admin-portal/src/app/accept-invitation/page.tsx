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
import { LactevaLockup } from "@/components/lockup";
import {acceptInvitation,
  describeError,
} from "@/lib/api";

/**
 * Join the organization you were invited to (LACTEVA-ADMIN-002).
 *
 * Public, because the person filling it in has no account yet — that is what
 * this page creates. It mirrors `/login`'s centred card deliberately: it is
 * the second page a new colleague ever sees, and the first is the one they are
 * sent to afterwards.
 *
 * The code is typed, not carried in the URL. A token in a query string ends up
 * in browser history, in the referrer of anything the page loads, and in every
 * access log between here and the server — for a credential that creates an
 * account with a role attached. The invitee reads it from their email and
 * types it, and this page holds it in component state for the length of one
 * request (SEC-003).
 *
 * Deliberately English (Decision D-1): this is a new, unwired surface, so its
 * strings stay plain rather than half-wiring a catalog nobody reads yet.
 */
const MIN_PASSWORD = 10;

export default function AcceptInvitationPage() {
  const [code, setCode] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await acceptInvitation(code.trim(), fullName.trim(), password);
      // The account exists now; say so before leaving, so the navigation is
      // not the only evidence it worked.
      setDone(true);
      // A FULL navigation, for the same reason `/login` uses one: `AppShell`
      // probes the session when it mounts, and a client-side push would not
      // remount it.
      window.location.assign("/login");
    } catch (err) {
      // The platform's own sentence. "That invitation has already been used"
      // and "that invitation has expired" send a person to different places —
      // one to their inbox, one to their administrator — so neither is
      // flattened into "invalid code" here.
      setError(
        describeError(err, "Could not reach the platform. Check your connection and try again."),
      );
      // The form KEEPS what was typed. Retyping a long code because the name
      // field was wrong is the kind of small cruelty software does casually.
    } finally {
      setBusy(false);
    }
  }

  return (
    // WO-39: the same front-door family as /login — the one generated
    // lockup on the DS's own dairy wash, arriving on the settle token. The
    // flow below and its enumeration-safe copy are untouched.
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-[image:var(--gradient-cream-fresh)] p-8">
      <LactevaLockup withTagline idPrefix="accept-invitation" className="lacteva-settle" />
      <Card className="lacteva-settle w-full max-w-sm">
        <CardHeader>
          <CardTitle>Accept your invitation</CardTitle>
          <CardDescription>
            Enter the code from your invitation email and choose a password.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="code">Invitation code</Label>
              <Input
                id="code"
                required
                autoComplete="off"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="full-name">Full name</Label>
              <Input
                id="full-name"
                required
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
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
            {done && (
              <p className="text-sm text-muted-foreground">
                Account created — taking you to sign in.
              </p>
            )}
            <Button type="submit" disabled={busy}>
              {busy ? "Joining…" : "Join"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
