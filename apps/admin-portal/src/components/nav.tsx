"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  type Session,
  actingTenant,
  can,
  clearActingTenant,
  getSession,
  logout,
  setActingTenant,
} from "@/lib/api";

/**
 * The navigation bar, and the one place that asks who is signed in.
 *
 * NAV-001: every destination needs a session, so the links appear only when
 * there is one. Signed out, the bar carries the product name and a way in.
 *
 * PERM-001: and only the destinations this session can actually USE. The bar
 * used to offer all eighteen to anybody signed in, so a tenant-viewer was
 * invited to open Users and Roles and got 403 from both. A menu is a promise;
 * offering something the platform will refuse is a promise the portal cannot
 * keep. Each entry names the permission its page needs, checked against the
 * session's own list — nothing is assumed about what a role contains.
 */

type Entry = { href: string; label: string; permission: string };

// Keys taken from the platform's own registry (`GET /v1/authz/permissions`),
// not invented: every one of these was guessed wrong the first time, which
// would have hidden the whole menu from the very users it is meant to serve.
const WORK: Entry[] = [
  { href: "/centers", label: "Centers", permission: "collection.center.read" },
  { href: "/suppliers", label: "Suppliers", permission: "supplier.read" },
  { href: "/transactions", label: "Transactions", permission: "collection.transaction.read" },
  { href: "/rate-cards", label: "Rate cards", permission: "pricing.ratecard.read" },
  { href: "/matrices", label: "Matrices", permission: "pricing.ratecard.read" },
  { href: "/resolve", label: "Playground", permission: "pricing.ratecard.read" },
  { href: "/settlements", label: "Settlements", permission: "settlement.read" },
  { href: "/payments", label: "Payments", permission: "payment.read" },
  { href: "/receipts", label: "Receipts", permission: "receipt.read" },
  { href: "/reports", label: "Reports", permission: "reporting.read" },
  { href: "/notifications", label: "Notifications", permission: "notification.read" },
  { href: "/sync", label: "Sync", permission: "sync.read" },
];

const ADMIN: Entry[] = [
  { href: "/admin/users", label: "Users", permission: "identity.user.read" },
  { href: "/admin/roles", label: "Roles", permission: "authz.role.read" },
  { href: "/admin/organizations", label: "Organizations", permission: "organization.read" },
  { href: "/admin/audit", label: "Audit", permission: "audit.read" },
  { href: "/admin/configuration", label: "Configuration", permission: "configuration.read" },
  { href: "/admin/operations", label: "Operations", permission: "platform.relay.manage" },
];

export function Nav() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);
  const [tenantInput, setTenantInput] = useState("");
  const [tenantError, setTenantError] = useState<string | null>(null);

  const load = () =>
    getSession()
      .then((s) => setSession(s))
      .catch(() => setSession({ authenticated: false }))
      .finally(() => setChecked(true));

  useEffect(() => {
    let cancelled = false;
    getSession()
      .then((s) => !cancelled && setSession(s))
      .catch(() => !cancelled && setSession({ authenticated: false }))
      .finally(() => !cancelled && setChecked(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const signedIn = checked && session?.authenticated === true;
  const scoped = actingTenant(session);
  // TENANT-001: a platform session carries no tenant of its own, so every
  // tenant-scoped page answers 403 until one is chosen.
  const needsTenant =
    signedIn && session?.authenticated === true && session.tenant_id === null && !scoped;

  const visible = [...WORK, ...ADMIN].filter((e) => can(session, e.permission));

  return (
    <nav className="border-b border-border bg-background/95 px-8 py-2 text-sm">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-1">
        <Link className="font-semibold" href="/">
          Lacteva
        </Link>

        {signedIn
          ? visible.map((e) => (
              <a key={e.href} className="text-muted-foreground hover:text-foreground" href={e.href}>
                {e.label}
              </a>
            ))
          : null}

        {!checked ? (
          <span className="ml-auto" />
        ) : signedIn && session?.authenticated ? (
          <span className="ml-auto flex items-center gap-3">
            {session.tenant_id === null ? (
              <span className="flex items-center gap-2">
                <span className="text-muted-foreground">
                  {scoped ? `acting in ${scoped.slice(0, 8)}…` : "no organization"}
                </span>
                {scoped ? (
                  <button
                    type="button"
                    className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    onClick={async () => {
                      await clearActingTenant();
                      await load();
                      router.refresh();
                    }}
                  >
                    leave
                  </button>
                ) : null}
              </span>
            ) : null}
            <span className="text-muted-foreground" title={session.user.email}>
              {session.user.full_name || session.user.email}
            </span>
            <button
              type="button"
              className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              onClick={async () => {
                await logout();
                setSession({ authenticated: false });
                router.push("/login");
                router.refresh();
              }}
            >
              Sign out
            </button>
          </span>
        ) : (
          <a className="ml-auto text-muted-foreground hover:text-foreground" href="/login">
            Sign in
          </a>
        )}
      </div>

      {/* A platform administrator has every permission and no organization, so
          without this they get 403 from every business page — which is exactly
          how this portal behaved. There is no "list all tenants" call on the
          platform, and inventing one here would build a capability the API has
          deliberately not given, so the organization is named. */}
      {needsTenant ? (
        <div className="mx-auto mt-2 flex max-w-6xl flex-wrap items-center gap-2 border-t border-border pt-2">
          <span className="text-muted-foreground">
            Platform session — choose an organization to work inside:
          </span>
          <input
            aria-label="Organization ID"
            className="h-8 min-w-80 rounded-md border border-input bg-transparent px-2 font-mono text-xs"
            placeholder="organization UUID"
            value={tenantInput}
            onChange={(e) => setTenantInput(e.target.value)}
          />
          <button
            type="button"
            className="h-8 rounded-md border border-input px-3 hover:bg-muted"
            onClick={async () => {
              setTenantError(null);
              try {
                await setActingTenant(tenantInput.trim());
                setTenantInput("");
                await load();
                router.refresh();
              } catch (err) {
                setTenantError(err instanceof Error ? err.message : "Could not set the organization");
              }
            }}
          >
            Use
          </button>
          {tenantError ? (
            <span role="alert" className="text-destructive">
              {tenantError}
            </span>
          ) : null}
        </div>
      ) : null}
    </nav>
  );
}
