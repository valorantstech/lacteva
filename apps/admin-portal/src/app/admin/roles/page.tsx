"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { TableSkeleton, CappedNotice,} from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type Center,
  type Member,
  type Role,
  type User,
  assignRole,
  createRole,
  listCenters,
  listPeople,
  listPermissions,
  listRoles,
  revokeRole,
  describeError,
} from "@/lib/api";

/**
 * Roles and permissions (PORTAL-001 / F-09, rebuilt in DEMO-008).
 *
 * What changed, and why it was worth changing:
 *
 * The page used to open with
 *
 *     const SYSTEM_ROLES = ["tenant-admin", "tenant-operator", "tenant-viewer"];
 *
 * — a list compiled into the bundle. It was wrong: `tenant-operator` has never
 * existed on this platform, so the page offered an administrator a role that
 * could not be granted, and the grant failed at the API with a message about a
 * role that was not found. It could not have been right for long either way,
 * because nothing kept it in step with the database.
 *
 * The reason it was hard-coded is that there was no way to ask: the backend had
 * `POST /v1/authz/roles` and no `GET`. DEMO-008 added the read, so this page now
 * shows the roles that exist, the permissions each one actually carries, and how
 * many people hold it.
 *
 * The page still hides nothing that matters. Every grant it offers is checked
 * again by the backend on the request it sends, and a person who reaches this
 * URL without `authz.role.manage` is refused there — the navigation not showing
 * it is a courtesy, not the boundary.
 */
export default function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Record<string, string>>({});
  const [people, setPeople] = useState<Array<Member & { user: User | null }>>(
    [],
  );
  const [centers, setCenters] = useState<Center[]>([]);
  // LACTEVA-ADMIN-007: the platform's own count, so a capped list can say so.
  const [centreTotal, setCentreTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [userId, setUserId] = useState("");
  const [roleName, setRoleName] = useState("");
  const [centerId, setCenterId] = useState("");
  const [newRole, setNewRole] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  // LACTEVA-ADMIN-001: `roles` starts `[]`, so before the first fetch settles
  // the table could not tell "none readable" from "not asked yet" — and it
  // was asserting the first, which reads as a permission failure.
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [defined, perms, staff] = await Promise.all([
        listRoles(),
        listPermissions(),
        listPeople(),
      ]);
      setRoles(defined);
      setPermissions(perms);
      setPeople(staff);
      setRoleName((current) => current || (defined[0]?.name ?? ""));
      setError(null);
    } catch (err) {
      setError(describeError(err, "Failed to load roles"));
    } finally {
      setLoading(false);
    }
    // Centres are only needed to scope a grant; their absence must not blank
    // the page.
    listCenters({ limit: 100, offset: 0 })
      .then((c) => {
        setCenters(c.items ?? []);
        setCentreTotal(c.total ?? 0);
      })
      .catch(() => setCenters([]));
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  async function run(what: string, action: () => Promise<unknown>) {
    setNote(null);
    setError(null);
    try {
      await action();
      setNote(what);
      await refresh();
    } catch (err) {
      setError(describeError(err, "The change was refused"));
    }
  }

  const permissionKeys = useMemo(
    () => Object.keys(permissions).sort(),
    [permissions],
  );

  // Design System V1 (batch F): the quiet-label treatment `DataTable` gives
  // its column headers, applied here because this page uses the raw `Table`
  // primitive. Kept page-local for the same reason as the /admin/users pilot —
  // `DataTable` already styles its own heads, so pushing this into `TableHead`
  // would double the treatment everywhere else.
  return (
    <AdminPage
      title="Roles and permissions"
      description={
        "Every role below is a row in the database, and every permission on it is checked " +
        "again by the backend on the request it authorises. Revoking takes effect on that " +
        "person's very next request — there is no permission cache."
      }
      error={error}
      note={note}
    >
      {/* --- what exists ---------------------------------------------------- */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Defined roles</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Role
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Description
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Scope
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground text-end">
                Permissions
              </TableHead>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground text-end">
                Held by
              </TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && roles.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <TableSkeleton columns={6} rows={5} />
                </TableCell>
              </TableRow>
            ) : roles.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground">
                  No roles are readable with this session.
                </TableCell>
              </TableRow>
            ) : (
              roles.map((role) => (
                <>
                  <TableRow key={role.id}>
                    <TableCell className="font-medium">{role.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {role.description || "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={role.system ? "secondary" : "outline"}>
                        {role.system ? "platform" : "this organization"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-end tabular-nums">
                      {role.permissions.includes("*")
                        ? "all"
                        : role.permissions.length}
                    </TableCell>
                    <TableCell className="text-end tabular-nums">
                      {role.assignments}
                    </TableCell>
                    <TableCell className="text-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setExpanded(expanded === role.id ? null : role.id)
                        }
                      >
                        {expanded === role.id ? "Hide" : "Show"}
                      </Button>
                    </TableCell>
                  </TableRow>
                  {expanded === role.id ? (
                    <TableRow key={`${role.id}-perms`}>
                      <TableCell colSpan={6}>
                        <div className="flex flex-wrap gap-1.5 py-1">
                          {role.permissions.map((key) => (
                            <span
                              key={key}
                              title={permissions[key] ?? ""}
                              className="rounded bg-muted px-2 py-0.5 font-mono text-xs"
                            >
                              {key === "*" ? "* (every permission)" : key}
                            </span>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </>
              ))
            )}
          </TableBody>
        </Table>
      </section>

      {/* --- grant / revoke -------------------------------------------------- */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Assign or revoke</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="user">User</Label>
            <Select
              id="user"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            >
              <option value="">Select a user…</option>
              {people.map((p) => (
                <option key={p.user_id} value={p.user_id}>
                  {p.user?.email ?? p.user_id}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role">Role</Label>
            <Select
              id="role"
              value={roleName}
              onChange={(e) => setRoleName(e.target.value)}
            >
              {roles.map((r) => (
                <option key={r.id} value={r.name}>
                  {r.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="scope">Centre scope</Label>
            <Select
              id="scope"
              value={centerId}
              onChange={(e) => setCenterId(e.target.value)}
            >
              <option value="">Whole organization</option>
              {centers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
            <CappedNotice
              shown={centers.length}
              total={centreTotal}
              noun="centres"
              hint="Search on the Centres page to find one that is not listed."
            />
          </div>
          <Button
            disabled={!userId || !roleName}
            onClick={() =>
              void run(
                centerId
                  ? `Granted ${roleName}, limited to one centre.`
                  : `Granted ${roleName} across the organization.`,
                () => assignRole(userId, roleName, centerId || null),
              )
            }
          >
            Grant
          </Button>
          <Button
            variant="destructive"
            disabled={!userId || !roleName}
            onClick={() =>
              void run(
                `Revoked ${roleName}. It stops applying immediately.`,
                () => revokeRole(userId, roleName),
              )
            }
          >
            Revoke
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          A centre scope narrows the grant to one collection centre: the holder
          may act there and nowhere else. Leave it on &ldquo;whole
          organization&rdquo; for roles that are not centre-specific.
        </p>
      </section>

      {/* --- define a role --------------------------------------------------- */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">
          Define a role for this organization
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-role">Name</Label>
            <Input
              id="new-role"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              placeholder="e.g. weighbridge-supervisor"
            />
          </div>
          <Button
            disabled={!newRole || selected.length === 0}
            onClick={() =>
              void run(
                `Created ${newRole} with ${selected.length} permissions.`,
                async () => {
                  await createRole(newRole, selected);
                  setNewRole("");
                  setSelected([]);
                },
              )
            }
          >
            Create role
          </Button>
        </div>
        <div className="grid max-h-72 grid-cols-1 gap-1 overflow-y-auto rounded-md border p-3 sm:grid-cols-2">
          {permissionKeys.map((key) => (
            <label key={key} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={selected.includes(key)}
                onChange={(e) =>
                  setSelected((current) =>
                    e.target.checked
                      ? [...current, key]
                      : current.filter((k) => k !== key),
                  )
                }
              />
              <span>
                <span className="font-mono text-xs">{key}</span>
                <span className="block text-xs text-muted-foreground">
                  {permissions[key]}
                </span>
              </span>
            </label>
          ))}
        </div>
      </section>
    </AdminPage>
  );
}
