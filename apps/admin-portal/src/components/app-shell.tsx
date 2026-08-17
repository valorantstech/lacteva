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
  BadgeCheck,
  CalendarDays,
  Banknote,
  Bell,
  Boxes,
  Building2,
  ChevronDown,
  ClipboardList,
  Map,
  Cog,
  FileText,
  Gauge,
  Globe,
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
  UserRound,
  Users,
  Wallet,
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
import { LocaleProvider, translatorFor, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * DEMO-013: `labelKey` rather than `label`.
 *
 * The navigation used to hold English sentences. A menu is the most visible
 * text in the product, so it is the first thing that has to stop being written
 * in one language — and a key is also what makes adding a language a catalog
 * entry rather than an edit here.
 */
type Entry = {
  href: string;
  labelKey: string;
  permission: string;
  icon: React.ElementType;
};

const OPERATIONS: Entry[] = [
  {
    href: "/",
    labelKey: "nav.dashboard",
    permission: "*dashboard",
    icon: Gauge,
  },
  {
    href: "/centers",
    labelKey: "nav.centers",
    permission: "collection.center.read",
    icon: Building2,
  },
  {
    href: "/suppliers",
    labelKey: "nav.suppliers",
    permission: "supplier.read",
    icon: Truck,
  },
  {
    href: "/transactions",
    labelKey: "nav.transactions",
    permission: "collection.transaction.read",
    icon: ClipboardList,
  },
];

// DEMO-009 — the customer side. Permission-gated like every other entry, so a
// collection operator (who has no sales.* grant) never sees it.
const SALES: Entry[] = [
  {
    href: "/customers",
    labelKey: "nav.customers",
    permission: "sales.customer.read",
    icon: UserRound,
  },
  {
    href: "/deliveries",
    labelKey: "nav.deliveries",
    permission: "sales.delivery.read",
    icon: Truck,
  },
  // DEMO-034 — the physical layer under the round. Gated on the route grant,
  // so a finance officer never sees it.
  {
    href: "/routes",
    labelKey: "nav.routes",
    permission: "logistics.route.read",
    icon: Map,
  },
  {
    href: "/billing",
    labelKey: "nav.billing",
    permission: "sales.invoice.read",
    icon: FileText,
  },
  // DEMO-010. `reporting.read`, not a sales permission — it is a report, and
  // an auditor with reporting access should reach it without being granted
  // anything on the sales module itself.
  {
    href: "/receivables",
    labelKey: "nav.receivables",
    permission: "reporting.read",
    icon: Wallet,
  },
];

const PRICING: Entry[] = [
  {
    href: "/rate-cards",
    labelKey: "nav.rateCards",
    permission: "pricing.ratecard.read",
    icon: Tags,
  },
  {
    href: "/matrices",
    labelKey: "nav.matrices",
    permission: "pricing.ratecard.read",
    icon: Grid3x3,
  },
  {
    href: "/resolve",
    labelKey: "nav.playground",
    permission: "pricing.ratecard.read",
    icon: Boxes,
  },
];

const FINANCE: Entry[] = [
  {
    href: "/settlements",
    labelKey: "nav.settlements",
    permission: "settlement.read",
    icon: Handshake,
  },
  {
    href: "/payments",
    labelKey: "nav.payments",
    permission: "payment.read",
    icon: Banknote,
  },
  {
    href: "/receipts",
    labelKey: "nav.receipts",
    permission: "receipt.read",
    icon: Receipt,
  },
  {
    href: "/reports",
    labelKey: "nav.reports",
    permission: "reporting.read",
    icon: FileText,
  },
];

const PLATFORM: Entry[] = [
  {
    href: "/notifications",
    labelKey: "nav.notifications",
    permission: "notification.read",
    icon: Bell,
  },
  {
    href: "/sync",
    labelKey: "nav.sync",
    permission: "sync.read",
    icon: RefreshCw,
  },
  {
    // DEMO-026. Where an administrator sees the trial and what it covers.
    href: "/admin/subscription",
    labelKey: "nav.subscription",
    permission: "organization.subscription.read",
    icon: BadgeCheck,
  },
  {
    // DEMO-020. Read-only, and behind its own permission: a viewer may look at
    // the dairy's calendar without being able to close its books.
    href: "/admin/calendar",
    labelKey: "nav.calendar",
    permission: "organization.calendar.read",
    icon: CalendarDays,
  },
  {
    href: "/admin/users",
    labelKey: "nav.users",
    permission: "identity.user.read",
    icon: Users,
  },
  {
    href: "/admin/roles",
    labelKey: "nav.roles",
    permission: "authz.role.read",
    icon: KeyRound,
  },
  {
    href: "/admin/organizations",
    labelKey: "nav.organizations",
    permission: "organization.read",
    icon: Landmark,
  },
  {
    href: "/admin/audit",
    labelKey: "nav.audit",
    permission: "audit.read",
    icon: ScrollText,
  },
  {
    href: "/admin/configuration",
    labelKey: "nav.configuration",
    permission: "configuration.read",
    icon: Cog,
  },
  {
    href: "/admin/operations",
    labelKey: "nav.operations",
    permission: "platform.relay.manage",
    icon: Server,
  },
  // DEMO-013. `organization.read`, not the manage grant: seeing what currency
  // and clock your dairy runs on is not an administrative act, and the page
  // itself hides the controls that would be refused.
  {
    href: "/admin/settings",
    labelKey: "nav.settings",
    permission: "organization.read",
    icon: Globe,
  },
];

const GROUPS: { titleKey: string; entries: Entry[] }[] = [
  { titleKey: "nav.operations", entries: OPERATIONS },
  { titleKey: "nav.sales", entries: SALES },
  { titleKey: "nav.pricing", entries: PRICING },
  { titleKey: "nav.finance", entries: FINANCE },
  { titleKey: "nav.platform", entries: PLATFORM },
];

/** The dashboard needs a session but no particular permission. */
const visibleTo = (session: Session | null, entry: Entry) =>
  entry.permission === "*dashboard" ? true : can(session, entry.permission);

/**
 * The page the current path belongs to, if the nav knows it (P0-UX-001).
 *
 * A detail page like `/customers/abc` belongs to `/customers`, so the match is
 * by prefix with the more specific entry winning. Used to keep somebody OUT of
 * a page their role cannot use — the browser walkthrough found a driver
 * deep-linking to `/routes` and being offered the office's "Add a route" forms
 * with a raw permission-key error where data should be. The platform refused
 * everything (that part worked); the page just should not have promised it.
 */
const entryFor = (pathname: string): Entry | undefined => {
  const all = [...OPERATIONS, ...SALES, ...PRICING, ...FINANCE, ...PLATFORM];
  return all
    .filter((e) => pathname === e.href || pathname.startsWith(`${e.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];
};

/**
 * The calm refusal, in the dashboard banner's own words. A DRIVER gets one
 * extra sentence: their work genuinely lives somewhere else, and "not part of
 * your access" alone reads like a mistake to somebody holding a phone that
 * says otherwise.
 */
function NotYourArea({ session }: { session: Session | null }) {
  const t = useT();
  const driver = can(session, "logistics.run.execute");
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <div className="rounded-lg border border-border bg-background p-6">
        <p className="font-medium">{t("shell.notYourArea")}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("shell.notYourAreaDetail")}
        </p>
        {driver && (
          <p className="mt-3 text-sm">{t("shell.driverGoesMobile")}</p>
        )}
      </div>
    </div>
  );
}

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
  // DEMO-013: the person's own language, from the session. Not the browser's
  // — a shared machine in a dairy office would otherwise flip a supervisor's
  // screen because of what the last person's laptop was set to.
  const locale = session?.authenticated ? session.user.locale : "en";
  const org = session?.authenticated ? session.organization : null;
  const t = translatorFor(locale);
  const scoped = actingTenant(session);
  const needsTenant =
    signedIn &&
    session?.authenticated === true &&
    session.tenant_id === null &&
    !scoped;

  const groups = GROUPS.map((g) => ({
    ...g,
    entries: g.entries.filter((e) => visibleTo(session, e)),
  })).filter((g) => g.entries.length > 0);

  // Signed out — or the answer is not known yet. No rail, no destinations, no
  // promises. The sign-in link waits for `checked`: offering it before the
  // probe answers would flash "Sign in" at someone who already is.
  //
  // PERF (DEMO-007): this used to be an EARLY RETURN of a different tree, and
  // that was expensive in a way nothing on screen revealed. The session probe
  // is asynchronous, so every page rendered once inside the signed-out tree
  // and then again inside the signed-in one — and because `{children}` sat at
  // a different position in each, React unmounted and remounted the page.
  // Every screen therefore issued every one of its requests TWICE, about
  // 200ms apart, on every single load. The structure below keeps `<main>` in
  // one place and varies only the chrome around it, so the page mounts once.
  const signedOutHeader = (
    <header className="flex h-14 shrink-0 items-center border-b border-border px-6">
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
  );

  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-6 px-3 py-4">
      {groups.map((group) => (
        <div key={group.titleKey} className="flex flex-col gap-1">
          <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t(group.titleKey)}
          </p>
          {group.entries.map((entry) => {
            const Icon = entry.icon;
            const active =
              entry.href === "/"
                ? pathname === "/"
                : pathname.startsWith(entry.href);
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
                {t(entry.labelKey)}
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
      {signedIn ? (
        <aside className="hidden w-60 shrink-0 border-e border-sidebar-border bg-sidebar lg:block">
          <div className="flex h-14 items-center border-b border-sidebar-border px-6">
            <Link href="/" className="font-semibold tracking-tight">
              Lacteva
            </Link>
          </div>
          <div className="sticky top-0 max-h-[calc(100vh-3.5rem)] overflow-y-auto">
            {nav}
          </div>
        </aside>
      ) : null}

      {/* Mobile drawer */}
      {signedIn && mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/40"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute left-0 top-0 h-full w-64 overflow-y-auto border-e border-sidebar-border bg-sidebar">
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
        {signedIn ? (
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

            <OrganizationChip
              session={session}
              scoped={scoped}
              onLeave={load}
            />

            <div className="ml-auto flex items-center gap-3">
              {session?.authenticated ? (
                <span className="hidden text-end sm:block">
                  <span className="block text-sm leading-tight">
                    {session.user.full_name || session.user.email}
                  </span>
                  <span className="block text-xs leading-tight text-muted-foreground">
                    {session.tenant_id === null
                      ? "Platform administrator"
                      : "Organization member"}
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
        ) : (
          signedOutHeader
        )}

        {signedIn && needsTenant ? (
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
                    err instanceof Error
                      ? err.message
                      : "Could not set the organization",
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

        {/* One position, both states — see the note above `signedOutHeader`. */}
        <main
          className={signedIn ? "min-w-0 flex-1 bg-muted/20" : "min-w-0 flex-1"}
        >
          {/*
            DEMO-013: every page below renders in this person's language and
            this organization's currency and timezone. Provided once, here,
            because the shell is the only component that already holds the
            session — a page fetching `/v1/auth/me` again just to learn what
            language to speak would be a second answer to a question already
            answered, and one request per page to ask it.
          */}
          <LocaleProvider
            locale={locale}
            currency={org?.currency_code ?? null}
            timezone={org?.timezone ?? null}
          >
            {/* P0-UX-001: a page whose nav entry this role cannot use renders
                the calm refusal instead of office forms the platform will 403.
                Client-side courtesy only — the server's own guards are the
                security, and they were verified to hold without this. */}
            {(() => {
              const entry = signedIn ? entryFor(pathname) : undefined;
              if (entry && !visibleTo(session, entry)) {
                return <NotYourArea session={session} />;
              }
              return children;
            })()}
          </LocaleProvider>
        </main>
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
