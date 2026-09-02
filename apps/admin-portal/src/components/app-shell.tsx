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
  BookOpen,
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
  Milestone,
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
  // WO-56 — what came in, what went out, what that leaves. Gated on the
  // dispatch READ grant, which the person at the intake bay holds: seeing the
  // centre's own day is not the same authority as recording what left it.
  {
    href: "/day-book",
    labelKey: "nav.dayBook",
    permission: "operations.dispatch.read",
    icon: BookOpen,
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
  // P0-PRODUCT-VISIBILITY-001. An honest, non-interactive page that keeps
  // "available today" and "on the roadmap" visibly separate. It needs no
  // permission — knowing what is coming is not a privileged act — so it uses
  // the same always-visible sentinel as the dashboard.
  {
    href: "/roadmap",
    labelKey: "nav.roadmap",
    permission: "*roadmap",
    icon: Milestone,
  },
];

const GROUPS: { titleKey: string; entries: Entry[] }[] = [
  { titleKey: "nav.operations", entries: OPERATIONS },
  { titleKey: "nav.sales", entries: SALES },
  { titleKey: "nav.pricing", entries: PRICING },
  { titleKey: "nav.finance", entries: FINANCE },
  { titleKey: "nav.platform", entries: PLATFORM },
];

/**
 * The dashboard and the roadmap need a session but no particular permission —
 * a `*`-prefixed sentinel marks an entry every signed-in person may see.
 */
const visibleTo = (session: Session | null, entry: Entry) =>
  entry.permission.startsWith("*") ? true : can(session, entry.permission);

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
  // The Lacteva logo (LACTEVA-BRAND-004): the can, then the wordmark.
  //
  // Both halves are GENERATED. The can comes from `tools/brand/mark.py`; the
  // LACTEVA letterforms are the owner's artwork, traced from the binding
  // reference by `tools/brand/trace_wordmark.py`. Neither is drawn here and
  // neither is SET here — WO-31 Amendment 1 forbids a font-rendered
  // approximation of the wordmark on any committed surface, and until now
  // this header carried exactly that: the word "Lacteva" in whatever the UI
  // font happened to be.
  //
  // `tools/brand/check_inline.py` fails the build if either copy drifts.
  //
  // ONE COLOUR, on purpose. The artwork's navy would vanish against the dark
  // theme's card, and at the fourteen pixels this header gives it the VA
  // gradient is invisible anyway. Amendment 1's one-colour derivation is the
  // same outlines filled once, which is what `currentColor` does here — so
  // this is the approved derivation rather than a second wordmark.
  const brand = (
    <span className="flex items-center gap-2">
      <svg
        aria-hidden="true"
        viewBox="16 12 32 45"
        className="h-5 w-auto text-primary"
      >
        <path d="M22 12C28.667 12 35.333 12 42 12C42 13.333 42 14.667 42 16C43.333 16 44.667 16 46 16C46 18 46 20 46 22C44.667 22 43.333 22 42 22C42 22.667 42 23.333 42 24C46 27 48 32 48 37C48 41.667 48 46.333 48 51C48 54.314 45.314 57 42 57C35.333 57 28.667 57 22 57C18.686 57 16 54.314 16 51C16 46.333 16 41.667 16 37C16 32 18 27 22 24C22 23.333 22 22.667 22 22C20.667 22 19.333 22 18 22C18 20 18 18 18 16C19.333 16 20.667 16 22 16C22 14.667 22 13.333 22 12Z" fill="currentColor" />
        {/* Knocked back to the header's own ground, so the drop is a hole. */}
        <path d="M32 30C36.2 35.9 39.8 40.4 39.8 44.9C39.8 49.208 36.308 52.7 32 52.7C27.692 52.7 24.2 49.208 24.2 44.9C24.2 40.4 27.8 35.9 32 30Z" className="fill-card" />
      </svg>
      <svg aria-hidden="true" viewBox="26.16 27.84 596.72 83.23" className="h-3.5 w-auto">
        <path d="M26.5 28.23C25.54 32.3 26.16 37.25 26.17 41.5L26.2 69.5L26.2 98.5C26.22 102.44 25.64 107.04 26.5 110.77C31.08 111.33 35.87 110.98 40.5 110.99L65.5 111C72.32 111 83.28 111.99 89.5 110.54C90.04 106.27 90.24 100.73 89.5 96.48C85.07 95.58 80.08 96.02 75.5 96.07L42.5 95.94C41.11 91.5 42.05 79.86 42.05 74.5L41.99 28.5C38.4 27.16 30.51 27.69 26.5 28.23ZM140.73 28.5C138.42 31.32 137.26 34.97 135.5 38.14L123.94 60.5L105.79 95.5L98.11 110.5C101.72 111.75 111.57 111.47 115.32 110.5L127.01 87.5L147.5 47.85C150.23 49.73 151.54 54.59 153.04 57.5C157.15 65.45 161.66 73.25 165.17 81.5L164.5 82.1L160.5 82.12C154.75 82.21 148.44 81.54 142.83 82.5C139.84 86.08 138.18 91.29 136.11 95.5C138.98 96.76 143.23 96.13 146.5 96.11C154.78 96.06 164.43 95.16 172.5 96.39L179.5 110.52C183.55 111.56 193.09 111.72 197.02 110.5C193.12 101.2 187.8 92.59 183.5 83.48L174 64.5L170.17 57.5L160.27 38.5C158.76 35.26 157.3 31.24 155 28.5C151.26 27.2 144.53 27.32 140.73 28.5ZM276.5 110.55L276.5 96.47C272.97 95.72 269.16 96.07 265.5 96.07L243.5 96.07C239.6 96.08 235.34 96.53 231.5 95.71C228.68 95.12 226.06 94.02 223.5 92.79C206.53 84.6 208 50.04 227.5 44.16C233.05 42.49 238.76 42.86 244.5 42.86L264.5 42.84C268.26 42.86 272.44 43.27 276.04 42.5C276.93 38.15 276.72 32.98 276.32 28.5C270.99 26.86 262.37 27.94 256.5 27.94C240.16 27.93 225.76 25.94 211.5 35.26C189.13 49.88 191.6 90.94 213.5 104.93C225.91 112.85 241.47 111.01 255.5 111C262.25 110.99 269.96 111.93 276.5 110.55ZM289.5 28.06C288.24 31.38 288.67 38.8 289.23 42.5C291.19 43.07 293.4 42.83 295.5 42.82L317.5 42.83L318.37 43.5L318.51 110.5C321.98 111.33 330.5 111.76 333.8 110.5L333.92 63.5L333.96 43.5L334.5 42.95L353.5 42.85C356.71 42.87 360.64 43.4 363.66 42.5C364.25 38.73 364.68 31.54 363.5 28.09L289.5 28.06ZM377.5 28.05C376.13 32.56 377.04 41.4 377.05 46.5L377.06 86.5C377.06 92.09 376.09 106.39 377.5 110.86L422.5 110.99C428.51 110.99 439.95 112 445.16 110.5L445.23 96.5C441.38 95.46 436.61 96.07 432.5 96.07L407.5 96.05C402.6 96.11 397.27 96.6 392.5 95.72C391.81 91.69 391.82 80.42 392.5 76.35C397.03 75.59 401.88 75.96 406.5 75.98L429.5 75.98C433.58 75.98 438.34 76.54 442.15 75.5L442.23 62.5C438.94 61.67 435.02 62.08 431.5 62.08L406.5 62.07C401.93 62.1 396.87 62.69 392.5 61.63L392.5 43.2C397.28 42.3 402.58 42.88 407.5 42.86L444.5 42.73C445.59 39.69 445.44 31.13 444.5 28.06L377.5 28.05Z" fill="currentColor" />
        <path d="M454.99 28.5L479.82 80.5L493.83 110.5C498.01 111.92 503.93 111.03 508.5 110.97C510.96 107.62 512.43 103.34 514.04 99.5L522.35 81.5L546.99 28.5L546.5 27.89L530.5 27.93L529.85 28.5C528.37 30.51 527.5 33.16 526.63 35.5L520.83 48.5L501.5 90.81L484.29 53.5L477.47 38.5C476.01 34.95 474.49 31.28 472.5 28.05L455.5 27.94L454.99 28.5ZM568.5 28.16C565.84 32.23 563.77 36.99 561.86 41.5L553.64 58.5L528.83 110.5C533.03 111.84 540.89 111.25 545.5 110.84L568.95 61.5C571.01 56.96 572.94 52.29 575.5 48.01C578.8 52.38 581.99 60.36 584.13 65.5L594.88 87.5L605.5 110.67C609.13 111.3 619.68 111.7 622.88 110.5L617.24 98.5C611.89 85.48 604.63 73.43 599.04 60.5L583.33 28.5C579.15 27.12 572.99 27.6 568.5 28.16ZM575.5 78.3C573.21 82.64 570.67 86.92 568.9 91.5C567.17 97.17 569.69 101.67 575.5 102.86C582.46 101.58 584.83 97.72 582.5 90.77L576.5 78.6L575.5 78.3Z" fill="currentColor" />
      </svg>
      {/* The logo is a picture; the link still needs a name. */}
      <span className="sr-only">Lacteva</span>
    </span>
  );

  const signedOutHeader = (
    <header className="flex h-14 shrink-0 items-center border-b border-border bg-card/80 px-6 backdrop-blur">
      <Link href="/">{brand}</Link>
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
          <p className="px-3 pb-1 text-meta font-semibold uppercase tracking-wider text-muted-foreground">
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
                  // `relative` carries the active indicator below.
                  "relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm",
                  "transition-colors duration-[var(--motion-fast)] ease-[var(--ease-out-liquid)]",
                  active
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                {/*
                  Where you are, readable at a glance rather than by comparing
                  two tints. `inset-inline-start` so it stays on the leading
                  edge in Arabic — a physical `left` would put it on the wrong
                  side of the word.
                */}
                {active ? (
                  <span
                    aria-hidden="true"
                    className="absolute inset-y-1.5 start-0 w-0.5 rounded-full bg-primary"
                  />
                ) : null}
                <Icon
                  aria-hidden
                  className={cn("size-4 shrink-0", active && "text-primary")}
                />
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
            <Link href="/">{brand}</Link>
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
              {brand}
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
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur lg:px-6">
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
                    {/* WO-60: the person's ROLE, not the generic "Organization
                        member" that told everyone the same nothing. Platform
                        administrator keeps its wording. */}
                    {session.tenant_id === null
                      ? "Platform administrator"
                      : roleLabel(session)}
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
          className="min-w-0 flex-1 bg-background"
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


/**
 * What this person IS here, in their own words (WO-60).
 *
 * From the session's roles, which `/v1/auth/me` has always returned and the
 * shell has never read. A role name arrives as the registry spells it —
 * `CENTRE_MANAGER`, `tenant-admin` — so it is title-cased for reading and not
 * translated into a vocabulary of this file's own invention: the registry is
 * the authority on what these are called, and a second naming here would
 * disagree with the roles screen the first time one was added.
 *
 * More than one role is normal (a manager who also collects), so they are
 * listed. No role at all is also normal — a member whose grants come from
 * elsewhere — and "Organization member" is the honest answer to that, rather
 * than an empty line.
 */
function roleLabel(session: Session): string {
  if (!session.authenticated) return "";
  const names = (session.roles ?? [])
    .map((role) => role.name)
    .filter(Boolean)
    .map((name) =>
      name
        .replace(/[_-]+/g, " ")
        .toLowerCase()
        .replace(/\b\w/g, (letter) => letter.toUpperCase()),
    );
  const unique = Array.from(new Set(names));
  return unique.length ? unique.join(" · ") : "Organization member";
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
  const organization = session.organization;

  if (session.tenant_id !== null) {
    return (
      <span
        className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-sm"
        // WO-60: the full name, for a dairy whose name does not fit. The
        // visible text truncates; the title does not.
        title={organization?.name ?? undefined}
      >
        <Building2 aria-hidden className="size-3.5 text-muted-foreground" />
        {/* WO-60: the ORGANIZATION'S NAME. This said the literal word
            "Organization" — for a multi-tenant product, "which tenant am I
            in" has to be answerable at a glance, and for a demonstration it
            is the difference between a Kenyan and an Indian dairy on screen.
            The chevron is gone with it: it opened nothing, and a control that
            looks interactive and is not is the same defect as a disabled
            button teasing a capability (WO-51b). */}
        <span className="max-w-[14rem] truncate font-medium">
          {organization?.name ?? "Organization"}
        </span>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2 text-sm">
      <ShieldCheck aria-hidden className="size-4 text-muted-foreground" />
      <span className="text-muted-foreground" title={organization?.name ?? undefined}>
        {/* WO-60: an acting platform administrator sees the tenant's NAME.
            It used to be `acting in 8f3a2b1c…` — a truncated UUID, which
            names nothing to the person reading it. The name arrives because
            the session route now tells the platform which tenant is being
            acted in; the id remains the fallback for the moment before it
            does. */}
        {scoped
          ? `acting in ${organization?.name ?? `${scoped.slice(0, 8)}…`}`
          : "no organization"}
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
