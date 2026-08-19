"use client";

/**
 * Display-name resolution for the rows a page actually shows
 * (P1-PORTAL-SCALE-001).
 *
 * The audit found every list page prefetching the first 100 suppliers or
 * customers and rendering UUID fragments for anybody past that — a milk clerk
 * cannot act on `8f3c1a2b…`. The fix is the platform's `ids` filter: collect
 * the distinct ids on the CURRENT page (at most one page's worth), resolve
 * them in ONE request, cache what came back. No prefetch ceiling, no N+1.
 *
 * Honesty rule: an id the platform did not return — deleted, foreign, or
 * unknown — stays unresolved, and the caller keeps rendering its existing
 * truncated-id fallback rather than a fabricated name. Tenancy is untouched:
 * the request runs as the signed-in user and the platform narrows `ids` by
 * tenant before anything else, so a foreign id simply resolves to nothing.
 */

import { useEffect, useRef, useState } from "react";
import { listCustomers, listSuppliers } from "@/lib/api";

type Lookup = (ids: string[]) => Promise<Record<string, string>>;

const supplierLookup: Lookup = async (ids) => {
  const page = await listSuppliers({ ids, limit: Math.min(ids.length, 100), offset: 0 });
  return Object.fromEntries((page.items ?? []).map((s) => [s.id, s.full_name]));
};

const customerLookup: Lookup = async (ids) => {
  const page = await listCustomers({ ids, limit: Math.min(ids.length, 100), offset: 0 });
  return Object.fromEntries((page.items ?? []).map((c) => [c.id, c.name]));
};

function useResolvedNames(ids: (string | null | undefined)[], lookup: Lookup) {
  const [names, setNames] = useState<Record<string, string>>({});
  const cache = useRef<Record<string, string>>({});
  // A stable key so the effect reruns only when the set of ids changes, not
  // on every render that rebuilds the array.
  const wanted = [...new Set(ids.filter((id): id is string => Boolean(id)))].sort();
  const key = wanted.join(",");

  useEffect(() => {
    const missing = wanted.filter((id) => !(id in cache.current));
    if (missing.length === 0) return;
    let cancelled = false;
    // One request per page of ids; the platform caps a page at 100 and no
    // list page shows more rows than that.
    (async () => {
      try {
        for (let i = 0; i < missing.length; i += 100) {
          const chunk = missing.slice(i, i + 100);
          const resolved = await lookup(chunk);
          Object.assign(cache.current, resolved);
        }
        if (!cancelled) setNames({ ...cache.current });
      } catch {
        // Resolution is presentation, not data: on failure the page keeps its
        // honest truncated-id fallback and the next page change retries.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` IS the ids
  }, [key, lookup]);

  return names;
}

/** id → supplier full name, for exactly the ids passed. */
export const useSupplierNames = (ids: (string | null | undefined)[]) =>
  useResolvedNames(ids, supplierLookup);

/** id → customer name, for exactly the ids passed. */
export const useCustomerNames = (ids: (string | null | undefined)[]) =>
  useResolvedNames(ids, customerLookup);
