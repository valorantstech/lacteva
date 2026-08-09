"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
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
  ApiError,
  type Member,
  type User,
  assignRole,
  createRole,
  listPeople,
  listPermissions,
  revokeRole,
} from "@/lib/api";

const SYSTEM_ROLES = ["tenant-admin", "tenant-operator", "tenant-viewer"];

export default function RolesPage() {
  const [permissions, setPermissions] = useState<Record<string, string>>({});
  const [people, setPeople] = useState<Array<Member & { user: User | null }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [userId, setUserId] = useState("");
  const [roleName, setRoleName] = useState(SYSTEM_ROLES[0]);
  const [newRole, setNewRole] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [perms, staff] = await Promise.all([listPermissions(), listPeople()]);
      setPermissions(perms);
      setPeople(staff);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load roles");
    }
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
      setError(err instanceof ApiError ? err.detail : "The change was refused");
    }
  }

  return (
    <AdminPage
      title="Roles and permissions"
      description={
        "Roles carry permissions; assignments give a role to a person. Revoking takes " +
        "effect on that person's very next request — there is no permission cache."
      }
      error={error}
      note={note}
    >
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Assign or revoke</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="user">User</Label>
            <select
              id="user"
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            >
              <option value="">Select a user…</option>
              {people.map((p) => (
                <option key={p.user_id} value={p.user_id}>
                  {p.user?.email ?? p.user_id}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role">Role</Label>
            <Input id="role" value={roleName} onChange={(e) => setRoleName(e.target.value)} />
          </div>
          <Button
            disabled={!userId || !roleName}
            onClick={() =>
              void run(`Granted ${roleName}.`, () => assignRole(userId, roleName))
            }
          >
            Grant
          </Button>
          <Button
            variant="destructive"
            disabled={!userId || !roleName}
            onClick={() =>
              void run(`Revoked ${roleName}. It stops applying immediately.`, () =>
                revokeRole(userId, roleName),
              )
            }
          >
            Revoke
          </Button>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Define a role</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-role">Name</Label>
            <Input
              id="new-role"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              placeholder="weighbridge-clerk"
            />
          </div>
          <Button
            disabled={!newRole || selected.length === 0}
            onClick={() =>
              void run(`Created ${newRole} with ${selected.length} permission(s).`, async () => {
                await createRole(newRole, selected);
                setNewRole("");
                setSelected([]);
              })
            }
          >
            Create role
          </Button>
          <span className="text-sm text-muted-foreground">
            {selected.length} permission(s) selected
          </span>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Permission registry</h2>
        <p className="text-sm text-muted-foreground">
          The platform&apos;s complete vocabulary. A role can only carry keys from this list —
          an unknown key is refused when the role is created, not when it is first used.
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              <TableHead>Key</TableHead>
              <TableHead>Meaning</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(permissions).map(([key, meaning]) => (
              <TableRow key={key}>
                <TableCell>
                  <input
                    type="checkbox"
                    aria-label={`Include ${key}`}
                    checked={selected.includes(key)}
                    onChange={(e) =>
                      setSelected((prev) =>
                        e.target.checked ? [...prev, key] : prev.filter((k) => k !== key),
                      )
                    }
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">{key}</TableCell>
                <TableCell>{meaning}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </AdminPage>
  );
}
