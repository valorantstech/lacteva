"use client";

import { useCallback, useEffect, useState } from "react";
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
import {
  type BillLink,
  type CustomerLogin,
  describeError,
  getCustomerBillLink,
  getCustomerLogin,
  inviteCustomer,
  mintCustomerBillLink,
  revokeCustomerBillLink,
  withdrawCustomerInvitation,
} from "@/lib/api";

/**
 * The two ways a household reaches its own bill, from the customer's page
 * (WO-86): an app LOGIN, and a BILL LINK for the household that will never
 * install an app.
 *
 * Both are the platform's decisions rendered. The invitation code goes to the
 * household's email and is never shown here; the bill link's token is shown
 * exactly once, in the response that minted it, and the platform will not
 * repeat it — so the card copies it for the operator right then, and says so.
 *
 * The trade-off is written on the card rather than in a help page nobody
 * opens: a bill link is a bearer credential. Anyone holding it reads the
 * bills. That is the point (no password for a household that will not manage
 * one), and it is also the risk, and the one remedy — replace the link — is
 * the same button that made it.
 */
export function CustomerAccessCards({
  customerId,
  disabled = false,
  onNotice,
}: {
  customerId: string;
  disabled?: boolean;
  onNotice?: (message: string) => void;
}) {
  return (
    <section
      aria-label="Customer access"
      className="grid gap-4 lg:grid-cols-2"
    >
      <LoginCard customerId={customerId} disabled={disabled} onNotice={onNotice} />
      <BillLinkCard customerId={customerId} disabled={disabled} onNotice={onNotice} />
    </section>
  );
}

function LoginCard({
  customerId,
  disabled,
  onNotice,
}: {
  customerId: string;
  disabled: boolean;
  onNotice?: (message: string) => void;
}) {
  const [login, setLogin] = useState<CustomerLogin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setLogin(await getCustomerLogin(customerId));
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, [customerId]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  async function run(action: () => Promise<CustomerLogin>, message: string) {
    setBusy(true);
    setError(null);
    try {
      setLogin(await action());
      onNotice?.(message);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const state = login?.state ?? null;
  return (
    <Card data-testid="customer-login-card">
      <CardHeader>
        <CardTitle className="text-base">App login</CardTitle>
        <CardDescription>
          {state === null && !error
            ? "Checking…"
            : state === "active"
              ? `Signed up as ${login?.email ?? ""}. They see their own deliveries, bills and receipts in the Lacteva app, and nothing else.`
              : state === "suspended"
                ? `${login?.email ?? "This login"} has been deactivated.`
                : state === "invited"
                  ? `Invitation sent to ${login?.email ?? ""}; it expires ${login?.expires_at ? new Date(login.expires_at).toLocaleDateString() : "in 7 days"}. The code went to their email and is not shown here.`
                  : "No login yet. Invite the household by email; the account it creates is bound to this customer before it can read anything."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            The platform refused: {error}
          </p>
        ) : null}
        {state === "none" || state === "invited" ? (
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              const address = email.trim();
              if (!address) return;
              void run(
                () => inviteCustomer(customerId, address),
                state === "invited"
                  ? "A new invitation was sent; the earlier code no longer works."
                  : "Invitation sent. The household will find the code in their email.",
              ).then(() => setEmail(""));
            }}
          >
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor={`customer-invite-email-${customerId}`}>
                {state === "invited" ? "Send to a different email" : "Household email"}
              </Label>
              <Input
                id={`customer-invite-email-${customerId}`}
                type="email"
                required
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={disabled || busy}
              />
            </div>
            <Button type="submit" size="sm" disabled={disabled || busy}>
              {state === "invited" ? "Re-invite" : "Invite"}
            </Button>
            {state === "invited" ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={disabled || busy}
                onClick={() =>
                  void run(async () => {
                    await withdrawCustomerInvitation(customerId);
                    return getCustomerLogin(customerId);
                  }, "Invitation withdrawn. The code no longer works.")
                }
              >
                Withdraw
              </Button>
            ) : null}
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}

function BillLinkCard({
  customerId,
  disabled,
  onNotice,
}: {
  customerId: string;
  disabled: boolean;
  onNotice?: (message: string) => void;
}) {
  const [link, setLink] = useState<BillLink | null>(null);
  const [minted, setMinted] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setLink(await getCustomerBillLink(customerId));
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, [customerId]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  async function mint() {
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const result = await mintCustomerBillLink(customerId);
      const origin =
        typeof window !== "undefined" ? window.location.origin : "";
      setMinted(`${origin}/bill/${result.token}`);
      setLink(result);
      onNotice?.(
        link?.active
          ? "Bill link replaced. The old link stopped working."
          : "Bill link created. Copy it now — it is not shown again.",
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    setBusy(true);
    setError(null);
    try {
      await revokeCustomerBillLink(customerId);
      setLink(await getCustomerBillLink(customerId));
      setMinted(null);
      onNotice?.("Bill link revoked. It no longer opens anything.");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!minted) return;
    try {
      await navigator.clipboard.writeText(minted);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Card data-testid="customer-bill-link-card">
      <CardHeader>
        <CardTitle className="text-base">Bill link</CardTitle>
        <CardDescription>
          A web page of this customer&apos;s bills that opens without a login —
          for the household that will not install an app. Send it on WhatsApp
          or SMS.
          {link?.active ? (
            <>
              {" "}
              A link is live
              {link.last_seen_at
                ? `, last opened ${new Date(link.last_seen_at).toLocaleDateString()}`
                : " and has not been opened yet"}
              {link.expires_at
                ? `; it expires ${new Date(link.expires_at).toLocaleDateString()}`
                : ""}
              .
            </>
          ) : null}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Anyone who has this link can see this customer&apos;s bills — no
          password asked. Share it only with the household, and if it travels
          further than you meant, replace it: the old link stops working the
          moment a new one is made.
        </p>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            The platform refused: {error}
          </p>
        ) : null}
        {minted ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`customer-bill-link-${customerId}`}>
              Copy it now — the platform does not show it again
            </Label>
            <div className="flex gap-2">
              <Input
                id={`customer-bill-link-${customerId}`}
                readOnly
                value={minted}
                onFocus={(e) => e.currentTarget.select()}
              />
              <Button type="button" size="sm" variant="outline" onClick={() => void copy()}>
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={disabled || busy || link === null}
            onClick={() => void mint()}
          >
            {link?.active ? "Replace link" : "Create link"}
          </Button>
          {link?.active ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled || busy}
              onClick={() => void revoke()}
            >
              Revoke
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
