"use client";

/**
 * The application shell: sidebar, top bar, content (DEMO-001).
 *
 * Replaces the single horizontal strip of eighteen links. Eighteen destinations
 * in a row is a debugging tool; grouped in a rail with the organization and the
 * signed-in user always visible is a product. Nothing about permissions,
 * sessions or tenancy changes here — the rules PORTAL-001 established are kept
 * exactly and only re-presented:
 *
 *   NAV-001  every destination needs a session, so signed out shows none;
 *   PERM-001 only destinations this session may actually USE are offered,
 *            checked against the session's own permission list — a menu is a
 *            promise, and offering a page the platform will refuse breaks it;
 *   TENANT-001 a platform session carries no tenant, so it must choose one
 *            before any tenant-scoped page will answer.
 *
 * The permission keys below come from the platform's registry
 * (`GET /v1/authz/permissions`), not from guesswork: every one of them was
 * wrong the first time they were written from memory, which hid the entire
 * menu from the people it exists for.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Banknote,
  Bell,
  Boxes,
  Building2,
  ChevronDown,
  ClipboardList,
  Cog,
  FileText,
  Gauge,
  Grid3x3,
  Handshake,
  KeyRound,
  Landmark,
  Menu,
  Receipt,
  RefreshCw,
  ScrollText,
  Server,
  ShieldCheck,
  Tags,
  Truck,
  Users,
  X,
} from "lucide-react";
import {
  type Session,
  actingTenant,
  can,
  clearActingTenant,
  getSession,
  logout,
  setActingTenant,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Entry = { href: string; label: string; permission: string; icon: React.ElementType };

const OPERATIONS: Entry[] = [
  { href: "/", label: "Dashboard", permission: "*dashboard", icon: Gauge },
  { href: "/centers", label: "Centers", permission: "collection.center.read", icon: Building2 },
  { href: "/suppliers", label: "Suppliers", permission: "supplier.read", icon: Truck },
  {
    href: "/transactions",
    label: "Transactions",
    permission: "collection.transaction.read",
    icon: ClipboardList,
  },
];

const PRICING: Entry[] = [
  { href: "/rate-cards", label: "Rate cards", permission: "pricing.ratecard.read", icon: Tags },
  { href: "/matrices", label: "Matrices", permission: "pricing.ratecard.read", icon: Grid3x3 },
  { href: "/resolve", label: "Playground", permission: "pricing.ratecard.read", icon: Boxes },
];

const FINANCE: Entry[] = [
  { href: "/settlements", label: "Settlements", permission: "settlement.read", icon: Handshake },
  { href: "/payments", label: "Payments", permission: "payment.read", icon: Banknote },
  { href: "/receipts", label: "Receipts", permission: "receipt.read", icon: Receipt },
  { href: "/reports", label: "Reports", permission: "reporting.read", icon: FileText },
];

const PLATFORM: Entry[] = [
  { href: "/notifications", label: "Notifications", permission: "notification.read", icon: Bell },
  { href: "/sync", label: "Sync", permission: "sync.read", icon: RefreshCw },
  { href: "/admin/users", label: "Users", permission: "identity.user.read", icon: Users },
  { href: "/admin/roles", label: "Roles", permission: "authz.role.read", icon: KeyRound },
  {
    href: "/admin/organizations",
    label: "Organizations",
    permission: "organization.read",
    icon: Landmark,
  },
  { href: "/admin/audit", label: "Audit", permission: "audit.read", icon: ScrollText },
  {
    href: "/admin/configuration",
    label: "Configuration",
    permission: "configuration.read",
    icon: Cog,
  },
  {
    href: "/admin/operations",
    label: "Operations",
    permission: "platform.relay.manage",
    icon: Server,
  },
];

const GROUPS: { title: string; entries: Entry[] }[] = [
  { title: "Operations", entries: OPERATIONS },
  { title: "Pricing", entries: PRICING },
  { title: "Finance", entries: FINANCE },
  { title: "Platform", entries: PLATFORM },
];

/** The dashboard needs a session but no particular permission. */
const visibleTo = (session: Session | null, entry: Entry) =>
  entry.permission === "*dashboard" ? true : can(session, entry.permission);

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const [checked, setChecked] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [tenantInput, setTenantInput] = useState("");
  const [tenantError, setTenantError] = useState<string | null>(null);

  const load = () =>
    getSession()
      .then(setSession)
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
  const needsTenant =
    signedIn && session?.authenticated === true && session.tenant_id === null && !scoped;

  const groups = GROUPS.map((g) => ({
    ...g,
    entries: g.entries.filter((e) => visibleTo(session, e)),
  })).filter((g) => g.entries.length > 0);

  if (!signedIn) {
    // Signed out — or the answer is not known yet. No rail, no destinations,
    // no promises. The sign-in link waits for `checked`: offering it before
    // the probe answers would flash "Sign in" at someone who already is.
    return (
      <div className="flex min-h-full flex-col">
        <header className="flex items-center border-b border-border px-6 py-3">
          <Link href="/" className="font-semibold tracking-tight">
            Lacteva
          </Link>
          {checked ? (
            <a
              className="ml-auto text-sm text-muted-foreground hover:text-foreground"
              href="/login"
            >
              Sign in
            </a>
          ) : null}
        </header>
        <main className="flex-1">{children}</main>
      </div>
    );
  }

  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-6 px-3 py-4">
      {groups.map((group) => (
        <div key={group.title} className="flex flex-col gap-1">
          <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {group.title}
          </p>
          {group.entries.map((entry) => {
            const Icon = entry.icon;
            const active =
              entry.href === "/" ? pathname === "/" : pathname.startsWith(entry.href);
            return (
              <Link
                key={entry.href}
                href={entry.href}
                aria-current={active ? "page" : undefined}
                // Closing the drawer belongs on the click, not in an effect
                // reacting to the path: the drawer is a consequence of THIS
                // interaction, and a `setState` in an effect body cascades a
                // render for something the event already knows.
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <Icon aria-hidden className="size-4 shrink-0" />
                {entry.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex min-h-full">
      {/* Desktop rail */}
      <aside className="hidden w-60 shrink-0 border-r border-sidebar-border bg-sidebar lg:block">
        <div className="flex h-14 items-center border-b border-sidebar-border px-6">
          <Link href="/" className="font-semibold tracking-tight">
            Lacteva
          </Link>
        </div>
        <div className="sticky top-0 max-h-[calc(100vh-3.5rem)] overflow-y-auto">{nav}</div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/40"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute left-0 top-0 h-full w-64 overflow-y-auto border-r border-sidebar-border bg-sidebar">
            <div className="flex h-14 items-center justify-between border-b border-sidebar-border px-4">
              <span className="font-semibold tracking-tight">Lacteva</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Close navigation"
                onClick={() => setMobileOpen(false)}
              >
                <X className="size-4" />
              </Button>
            </div>
            {nav}
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/95 px-4 lg:px-6">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="size-4" />
          </Button>

          <OrganizationChip session={session} scoped={scoped} onLeave={load} />

          <div className="ml-auto flex items-center gap-3">
            {session?.authenticated ? (
              <span className="hidden text-right sm:block">
                <span className="block text-sm leading-tight">
                  {session.user.full_name || session.user.email}
                </span>
                <span className="block text-xs leading-tight text-muted-foreground">
                  {session.tenant_id === null ? "Platform administrator" : "Organization member"}
                </span>
              </span>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={async () => {
                await logout();
                setSession({ authenticated: false });
                router.push("/login");
                router.refresh();
              }}
            >
              Sign out
            </Button>
          </div>
        </header>

        {needsTenant ? (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/40 px-4 py-2.5 lg:px-6">
            <span className="text-sm text-muted-foreground">
              Platform session — choose an organization to work inside:
            </span>
            <input
              aria-label="Organization ID"
              className="h-8 min-w-80 rounded-md border border-input bg-background px-2 font-mono text-xs"
              placeholder="organization UUID"
              value={tenantInput}
              onChange={(e) => setTenantInput(e.target.value)}
            />
            <Button
              type="button"
              size="sm"
              onClick={async () => {
                setTenantError(null);
                try {
                  await setActingTenant(tenantInput.trim());
                  setTenantInput("");
                  await load();
                  router.refresh();
                } catch (err) {
                  setTenantError(
                    err instanceof Error ? err.message : "Could not set the organization",
                  );
                }
              }}
            >
              Use
            </Button>
            {tenantError ? (
              <span role="alert" className="text-sm text-destructive">
                {tenantError}
              </span>
            ) : null}
          </div>
        ) : null}

        <main className="min-w-0 flex-1 bg-muted/20">{children}</main>
      </div>
    </div>
  );
}

function OrganizationChip({
  session,
  scoped,
  onLeave,
}: {
  session: Session | null;
  scoped: string | null;
  onLeave: () => void;
}) {
  const router = useRouter();
  if (!session?.authenticated) return null;

  if (session.tenant_id !== null) {
    return (
      <span className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-sm">
        <Building2 aria-hidden className="size-3.5 text-muted-foreground" />
        <span className="font-medium">Organization</span>
        <ChevronDown aria-hidden className="size-3 text-muted-foreground" />
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2 text-sm">
      <ShieldCheck aria-hidden className="size-4 text-muted-foreground" />
      <span className="text-muted-foreground">
        {scoped ? `acting in ${scoped.slice(0, 8)}…` : "no organization"}
      </span>
      {scoped ? (
        <button
          type="button"
          className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          onClick={async () => {
            await clearActingTenant();
            onLeave();
            router.refresh();
          }}
        >
          leave
        </button>
      ) : null}
    </span>
  );
}
