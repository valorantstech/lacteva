"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { type Session, getSession, logout } from "@/lib/api";

/**
 * The navigation bar, and the one place that asks who is signed in (NAV-001).
 *
 * Every destination below needs a session: each page fetches tenant-scoped
 * data on mount, so following any of them while signed out produced a 401 and
 * a bounce straight back to /login. Showing a full menu to somebody who cannot
 * use a single item of it is an invitation to click and be rejected.
 *
 * So the links are rendered only when there IS a session. Signed out, the bar
 * carries the product name and a way in — which is all the login page needs.
 *
 * This also collapses two session probes into one. The bar used to be static
 * links plus a `SessionControls` island that asked separately; now the answer
 * is fetched once and decides the whole bar.
 */

const WORK = [
  ["/centers", "Centers"],
  ["/suppliers", "Suppliers"],
  ["/transactions", "Transactions"],
  ["/rate-cards", "Rate cards"],
  ["/matrices", "Matrices"],
  ["/resolve", "Playground"],
  ["/settlements", "Settlements"],
  ["/payments", "Payments"],
  ["/receipts", "Receipts"],
  ["/reports", "Reports"],
  ["/notifications", "Notifications"],
  ["/sync", "Sync"],
] as const;

const ADMIN = [
  ["/admin/users", "Users"],
  ["/admin/roles", "Roles"],
  ["/admin/organizations", "Organizations"],
  ["/admin/audit", "Audit"],
  ["/admin/configuration", "Configuration"],
  ["/admin/operations", "Operations"],
] as const;

export function Nav() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // SESSION-001: answers 200 either way, so being signed out is not an error.
    getSession()
      .then((s) => !cancelled && setSession(s))
      .catch(() => !cancelled && setSession(null))
      .finally(() => !cancelled && setChecked(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const signedIn = checked && session?.authenticated === true;

  return (
    <nav className="border-b border-border bg-background/95 px-8 py-2 text-sm">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-1">
        <Link className="font-semibold" href="/">
          Lacteva
        </Link>

        {/* Nothing is rendered until the answer is known: a menu that appears
            and then vanishes reads as a glitch, and one that appears for a
            signed-out visitor invites a click that cannot work. */}
        {signedIn
          ? [...WORK, ...ADMIN].map(([href, label]) => (
              <a
                key={href}
                className="text-muted-foreground hover:text-foreground"
                href={href}
              >
                {label}
              </a>
            ))
          : null}

        {!checked ? (
          <span className="ml-auto" />
        ) : signedIn && session?.authenticated ? (
          <span className="ml-auto flex items-center gap-3">
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
    </nav>
  );
}
