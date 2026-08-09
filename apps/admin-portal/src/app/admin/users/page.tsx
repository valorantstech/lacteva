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
import { ApiError, type Member, type User, listPeople, setUserActive } from "@/lib/api";

type Person = Member & { user: User | null };

export default function UsersPage() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setPeople(await listPeople());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load users");
    }
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

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
            <TableHead>Membership</TableHead>
            <TableHead>Account</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {people === null ? (
            <TableRow>
              <TableCell colSpan={5}>Loading…</TableCell>
            </TableRow>
          ) : people.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5}>No members yet.</TableCell>
            </TableRow>
          ) : (
            people.map((person) => (
              <TableRow key={person.user_id}>
                <TableCell>{person.user?.full_name ?? "—"}</TableCell>
                <TableCell>{person.user?.email ?? <em>account unavailable</em>}</TableCell>
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
                <TableCell className="text-right">
                  {person.user ? (
                    <Button
                      variant={person.user.is_active ? "destructive" : "default"}
                      disabled={busy === person.user_id}
                      onClick={() => void toggle(person)}
                    >
                      {person.user.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </AdminPage>
  );
}
