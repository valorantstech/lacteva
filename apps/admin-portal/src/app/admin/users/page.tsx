"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  type Center,
  type Member,
  type User,
  listCenters,
  listPeople,
  setMemberStatus,
  setUserActive,
} from "@/lib/api";

type Person = Member & { user: User | null };

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "never";

export default function UsersPage() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [centers, setCenters] = useState<Center[]>([]);

  const refresh = useCallback(async () => {
    try {
      setPeople(await listPeople());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load users");
    }
    // DEMO-008 §9: who holds what, and where. Roles carry their assignments;
    // the centre names turn a scope id into something readable. Neither may
    // blank the page if it fails.
    listCenters({ limit: 100, offset: 0 })
      .then((c) => setCenters(c.items ?? []))
      .catch(() => setCenters([]));
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  /**
   * Suspend or reinstate the MEMBERSHIP — distinct from deactivating the
   * account. Suspension says "not part of this organization right now" and
   * takes effect on the member's very next request; deactivation says "this
   * person may not sign in at all" and revokes every live session.
   */
  /** A centre id, as a name — the scope is meaningless as a uuid. */
  const centerName = (id: string) =>
    centers.find((c) => c.id === id)?.name ?? `${id.slice(0, 8)}…`;

  async function suspend(person: Person, status: "active" | "suspended") {
    setBusy(person.user_id);
    setNote(null);
    try {
      await setMemberStatus(person.user_id, status);
      setNote(
        status === "suspended"
          ? `${person.user?.email ?? "The member"} is suspended. It applies to their very next request.`
          : `${person.user?.email ?? "The member"} is reinstated.`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to change the membership");
    } finally {
      setBusy(null);
    }
  }

  async function toggle(person: Person) {
    if (!person.user) return;
    const next = !person.user.is_active;
    setBusy(person.user_id);
    setNote(null);
    try {
      await setUserActive(person.user_id, next);
      setNote(
        next
          ? `${person.user.email} can sign in again. They must log in — old sessions stay revoked.`
          : `${person.user.email} is deactivated. Every live session was revoked.`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to change the account");
    } finally {
      setBusy(null);
    }
  }

  return (
    <AdminPage
      title="Users"
      description={
        "People with access to this organization. Deactivating an account revokes " +
        "every live session immediately; it does not delete anything the person did."
      }
      error={error}
      note={note}
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Membership</TableHead>
            <TableHead>Account</TableHead>
            <TableHead>Last signed in</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {people === null ? (
            <TableRow>
              <TableCell colSpan={7}>Loading…</TableCell>
            </TableRow>
          ) : people.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7}>No members yet.</TableCell>
            </TableRow>
          ) : (
            people.map((person) => (
              <TableRow key={person.user_id}>
                <TableCell>{person.user?.full_name ?? "—"}</TableCell>
                <TableCell>{person.user?.email ?? <em>account unavailable</em>}</TableCell>
                <TableCell>
                  {(person.roles ?? []).length === 0 ? (
                    <span className="text-muted-foreground">no role</span>
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      {(person.roles ?? []).map((role) => (
                        <span key={`${role.name}-${role.center_id ?? "org"}`} className="text-sm">
                          {role.name}
                          <span className="ml-1 text-xs text-muted-foreground">
                            {role.center_id
                              ? `· ${centerName(role.center_id)}`
                              : "· whole organization"}
                          </span>
                        </span>
                      ))}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={person.status === "active" ? "default" : "secondary"}>
                    {person.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {person.user ? (
                    <Badge variant={person.user.is_active ? "default" : "destructive"}>
                      {person.user.is_active ? "active" : "deactivated"}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="tabular-nums text-sm text-muted-foreground">
                  {stamp(person.user?.last_login_at)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant={person.status === "active" ? "outline" : "default"}
                      disabled={busy === person.user_id}
                      onClick={() =>
                        void suspend(person, person.status === "active" ? "suspended" : "active")
                      }
                    >
                      {person.status === "active" ? "Suspend" : "Reinstate"}
                    </Button>
                    {person.user ? (
                      <Button
                        variant={person.user.is_active ? "destructive" : "default"}
                        disabled={busy === person.user_id}
                        onClick={() => void toggle(person)}
                      >
                        {person.user.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </AdminPage>
  );
}
