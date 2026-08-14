"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  type Me,
  type Organization,
  getMe,
  getOrganization,
} from "@/lib/api";

/**
 * The organization this session is acting inside (PORTAL-001 / F-10).
 *
 * Deliberately not a tenant LIST. Tenancy is enforced by row-level security:
 * a tenant-scoped session can see exactly one organization — its own — and a
 * page that appeared to list others would be describing a capability the
 * platform does not have and must not grow casually.
 */
export default function OrganizationsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [org, setOrg] = useState<Organization | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const session = await getMe();
      setMe(session);
      setOrg(
        session.tenant_id ? await getOrganization(session.tenant_id) : null,
      );
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Failed to load the organization",
      );
    }
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  return (
    <AdminPage
      title="Organization"
      description="The tenant this session acts inside, and the permissions it carries."
      error={error}
    >
      {me === null ? (
        <p>Loading…</p>
      ) : me.tenant_id === null ? (
        <p className="text-sm text-muted-foreground">
          This is a platform-level session with no organization bound. Sign in
          with an organization id, or send <code>X-Tenant-ID</code>, to act
          inside a tenant.
        </p>
      ) : (
        <Table>
          <TableBody>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableCell>{org?.name ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead>Slug</TableHead>
              <TableCell>{org?.slug ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead>Country</TableHead>
              <TableCell>{org?.country_code?.toUpperCase() ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead>Tenant id</TableHead>
              <TableCell className="font-mono text-xs">
                {me.tenant_id}
              </TableCell>
            </TableRow>
            <TableRow>
              <TableHead>Signed in as</TableHead>
              <TableCell>{me.user.email}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead>Permissions</TableHead>
              <TableCell className="flex flex-wrap gap-1">
                {me.permissions.length === 0 ? (
                  <span className="text-muted-foreground">none</span>
                ) : (
                  me.permissions.map((p) => (
                    <Badge
                      key={p}
                      variant="secondary"
                      className="font-mono text-[11px]"
                    >
                      {p}
                    </Badge>
                  ))
                )}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )}
    </AdminPage>
  );
}
