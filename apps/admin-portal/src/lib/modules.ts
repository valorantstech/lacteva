/**
 * The product modules an organisation has turned on (D-31 · WO-85).
 *
 * Owner decision D-31: "some dairy firm also have retail, they sell and
 * purchase both. so make everything customizable." An organisation is not a
 * dairy OR a shop; it has a LIST of modules, and the navigation is the union
 * of what the enabled modules contribute:
 *
 *  * `collection` — milk coming IN from suppliers: Centres, Suppliers,
 *    Transactions, Day book, Rate cards, Matrices, Playground, Settlements,
 *    and the SUPPLIER-side Payments and Receipts.
 *  * `sales` — milk going OUT to customers: Customers, Deliveries, Routes and
 *    runs, Billing, Who owes money, and Products (WO-81).
 *
 * Always visible, whatever is enabled: Dashboard, Reports, Notifications,
 * Sync, and everything under Admin.
 *
 * A REGISTRY, mirroring `core/modules.py` on the platform, so a third module
 * later is one entry here and one there — not a search through the codebase.
 * Each nav entry names its module; this file says what the modules are and
 * which a session has.
 *
 * Presentation only, and hiding is not security: a module that is off hides
 * its navigation and nothing else. The routes still exist, the permissions
 * still govern, and a shop's administrator who types `/settlements` still
 * gets the page with nothing in it — the same argument `app-shell.tsx` makes
 * about the permission filter.
 */
import type { Session } from "@/lib/api";

export type ModuleKey = "collection" | "sales";

export const MODULES: Record<ModuleKey, { labelKey: string; detailKey: string }> = {
  collection: { labelKey: "modules.collection", detailKey: "modules.collectionDetail" },
  sales: { labelKey: "modules.sales", detailKey: "modules.salesDetail" },
};

export const ALL_MODULES: ModuleKey[] = ["collection", "sales"];

/**
 * What this session's organisation has turned on.
 *
 * A session with no organisation block — a platform administrator who has
 * not chosen one, or a test session built without one — sees everything:
 * the absence of a list is not a shop, it is "nothing said", and the
 * navigation test that predates D-31 must keep passing byte for byte.
 */
export function enabledModules(session: Session | null | undefined): Set<ModuleKey> {
  const listed =
    session && session.authenticated && session.organization
      ? session.organization.modules
      : undefined;
  if (!listed || listed.length === 0) return new Set(ALL_MODULES);
  return new Set(listed.filter((m): m is ModuleKey => m === "collection" || m === "sales"));
}

/** Enabled for this session, or ungoverned (no module named). */
export function moduleEnabled(session: Session | null | undefined, module?: ModuleKey): boolean {
  return module === undefined || enabledModules(session).has(module);
}

/**
 * The organisation runs `sales` and NOT `collection`: the one shape in which
 * "collection centre" is a meaningless phrase to its owner, and the only
 * shape the label overrides apply to (D-31 §6). An organisation that does
 * both has a collection centre, and the existing word is correct.
 */
export function salesOnly(session: Session | null | undefined): boolean {
  const enabled = enabledModules(session);
  return enabled.has("sales") && !enabled.has("collection");
}
