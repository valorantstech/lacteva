"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminPage } from "@/components/admin-page";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
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
  type Center,
  type Member,
  type Role,
  type User,
  cancelMemberEmailChange,
  inviteMember,
  listCenters,
  listPeople,
  listRoles,
  requestMemberEmailChange,
  setMemberProfile,
  setMemberStatus,
  setUserActive,
  describeError,
} from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Person = Member & { user: User | null };

const stamp = (iso: string | null | undefined) =>
  iso ? String(iso).slice(0, 16).replace("T", " ") : "never";

export default function UsersPage() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [centers, setCenters] = useState<Center[]>([]);
  // LACTEVA-ADMIN-002. Onboarding a dairy's staff needed raw API calls until
  // now: the endpoint was implemented and SMTP-proven with no client caller.
  const [roles, setRoles] = useState<Role[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("tenant-viewer");
  const [inviting, setInviting] = useState(false);
  // WO-87 §4: which row is being edited, and how.
  const [editing, setEditing] = useState<
    | { user_id: string; kind: "name"; value: string }
    | { user_id: string; kind: "email"; value: string }
    | null
  >(null);

  const refresh = useCallback(async () => {
    try {
      setPeople(await listPeople());
      setError(null);
    } catch (err) {
      setError(describeError(err, "Failed to load users"));
    }
    // DEMO-008 §9: who holds what, and where. Roles carry their assignments;
    // the centre names turn a scope id into something readable. Neither may
    // blank the page if it fails.
    listCenters({ limit: 100, offset: 0 })
      .then((c) => setCenters(c.items ?? []))
      .catch(() => setCenters([]));
    // The roles the PLATFORM has, never a list compiled into the bundle —
    // the defect DEMO-008 found on the Roles page, not repeated here.
    listRoles()
      .then(setRoles)
      .catch(() => setRoles([]));
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
      setError(
        describeError(err, "Failed to change the membership"),
      );
    } finally {
      setBusy(null);
    }
  }

  /** WO-87 §2: a typo fix, audited with before and after. */
  async function saveName(person: Person, fullName: string) {
    setBusy(person.user_id);
    setNote(null);
    setError(null);
    try {
      await setMemberProfile(person.user_id, fullName.trim());
      setNote(`Name corrected to ${fullName.trim()}.`);
      setEditing(null);
      await refresh();
    } catch (err) {
      setError(describeError(err, "Failed to correct the name"));
    } finally {
      setBusy(null);
    }
  }

  /**
   * WO-87 §3: start an email change. The portal never sets the address: the
   * platform sends the NEW address a code, tells the OLD address, and only
   * the new address confirming makes it real.
   */
  async function changeEmail(person: Person, newEmail: string) {
    setBusy(person.user_id);
    setNote(null);
    setError(null);
    try {
      const pending = await requestMemberEmailChange(person.user_id, newEmail.trim());
      setNote(
        `A confirmation code was sent to ${pending.new_email}; ${person.user?.email ?? "the current address"} has been told. ` +
          `Nothing changes until the new address confirms — before ${stamp(pending.expires_at)}.`,
      );
      setEditing(null);
      await refresh();
    } catch (err) {
      setError(describeError(err, "Failed to start the email change"));
    } finally {
      setBusy(null);
    }
  }

  async function cancelEmail(person: Person) {
    setBusy(person.user_id);
    setNote(null);
    setError(null);
    try {
      await cancelMemberEmailChange(person.user_id);
      setNote("The email change was cancelled. The current address stays.");
      await refresh();
    } catch (err) {
      setError(describeError(err, "Failed to cancel the email change"));
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
      setError(
        describeError(err, "Failed to change the account"),
      );
    } finally {
      setBusy(null);
    }
  }

  /**
   * Invite someone (LACTEVA-ADMIN-002).
   *
   * The response carries no token by design (SEC-003): the code goes to the
   * invitee's inbox and nowhere else, so there is nothing here to show, copy
   * or accidentally log. What the administrator gets back is the fact of it
   * and the date it stops working.
   */
  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setNote(null);
    setError(null);
    try {
      const sent = await inviteMember(inviteEmail.trim(), inviteRole);
      setNote(
        `Invitation sent to ${sent.email} — expires ${stamp(sent.expires_at)}.`,
      );
      setInviteEmail("");
    } catch (err) {
      // A viewer without `organization.member.manage` lands here, and must
      // read the platform's sentence rather than watch nothing happen.
      setError(
        describeError(err, "Failed to send the invitation"),
      );
    } finally {
      setInviting(false);
    }
  }

  // Design System V1 (batch C pilot): the same quiet-label treatment
  // `DataTable` now gives its column headers, applied here because this page
  // uses the raw `Table` primitive. Deliberately NOT pushed into `TableHead`
  // itself — `DataTable` already styles its own heads, and doing both would
  // double the treatment on ten other pages.
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
      <form onSubmit={invite} className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="invite-email">Invite by email</Label>
          <Input
            id="invite-email"
            type="email"
            required
            className="min-w-72"
            placeholder="colleague@dairy.example"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="invite-role">Role</Label>
          <Select
            id="invite-role"
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value)}
          >
            {roles.map((role) => (
              <option key={role.id} value={role.name}>
                {role.name}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" disabled={inviting || !inviteEmail}>
          {inviting ? "Sending…" : "Send invitation"}
        </Button>
        <p className="w-full text-xs text-muted-foreground">
          The invitation carries a one-time code to that address. Centre-scoped
          assignment happens on the Roles page once the person has joined.
        </p>
        {/* WO-87 §5: what is NOT on offer, said before somebody tries it. */}
        <p className="w-full text-xs text-muted-foreground" data-testid="users-help">
          A name can be corrected here, and an email changed — the new address must
          confirm from its inbox, and the old address is told. A login cannot be moved
          to a different person: when someone leaves and another takes their round,
          deactivate the account and invite the new person, because the deliveries,
          runs and audit lines belong to whoever made them.
        </p>
      </form>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">Name</TableHead>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">Email</TableHead>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">Role</TableHead>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">Membership</TableHead>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">Account</TableHead>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">Last signed in</TableHead>
            <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground text-end">Action</TableHead>
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
                <TableCell>
                  {editing?.user_id === person.user_id && editing.kind === "name" ? (
                    <form
                      className="flex items-center gap-1"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void saveName(person, editing.value);
                      }}
                    >
                      <Input
                        aria-label="Name"
                        className="h-8 min-w-40"
                        value={editing.value}
                        onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                        autoFocus
                      />
                      <Button type="submit" size="sm" disabled={busy === person.user_id || !editing.value.trim()}>
                        Save
                      </Button>
                      <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>
                        Cancel
                      </Button>
                    </form>
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      {person.user?.full_name ?? "—"}
                      {person.user ? (
                        <button
                          type="button"
                          className="text-xs text-muted-foreground underline underline-offset-4"
                          aria-label={`Edit name of ${person.user.full_name}`}
                          onClick={() =>
                            setEditing({ user_id: person.user_id, kind: "name", value: person.user!.full_name })
                          }
                        >
                          edit
                        </button>
                      ) : null}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  {editing?.user_id === person.user_id && editing.kind === "email" ? (
                    <form
                      className="flex flex-col gap-1"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void changeEmail(person, editing.value);
                      }}
                      data-testid={`email-change-${person.user_id}`}
                    >
                      <div className="flex items-center gap-1">
                        <Input
                          aria-label="New email"
                          type="email"
                          className="h-8 min-w-56"
                          value={editing.value}
                          onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                          autoFocus
                        />
                        <Button type="submit" size="sm" disabled={busy === person.user_id || !editing.value.trim()}>
                          Send code
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>
                          Cancel
                        </Button>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        The new address gets a code and must confirm from its inbox; the
                        current address is told now. Until then the current address keeps
                        signing in. On confirmation every session is signed out.
                      </span>
                    </form>
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      <span className="inline-flex items-center gap-1">
                        {person.user?.email ?? <em>account unavailable</em>}
                        {person.user && !person.pending_email_change ? (
                          <button
                            type="button"
                            className="text-xs text-muted-foreground underline underline-offset-4"
                            aria-label={`Change email of ${person.user.full_name}`}
                            onClick={() => setEditing({ user_id: person.user_id, kind: "email", value: "" })}
                          >
                            change
                          </button>
                        ) : null}
                      </span>
                      {person.pending_email_change ? (
                        <span
                          className="text-xs text-muted-foreground"
                          data-testid={`pending-email-${person.user_id}`}
                        >
                          changing to {person.pending_email_change.new_email} — awaiting
                          confirmation, expires {stamp(person.pending_email_change.expires_at)}{" "}
                          <button
                            type="button"
                            className="underline underline-offset-4"
                            disabled={busy === person.user_id}
                            onClick={() => void cancelEmail(person)}
                          >
                            cancel
                          </button>
                        </span>
                      ) : null}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  {(person.roles ?? []).length === 0 ? (
                    <span className="text-muted-foreground">no role</span>
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      {(person.roles ?? []).map((role) => (
                        <span
                          key={`${role.name}-${role.center_id ?? "org"}`}
                          className="text-sm"
                        >
                          {role.name}
                          <span className="ms-1 text-xs text-muted-foreground">
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
                  <Badge
                    variant={
                      person.status === "active" ? "default" : "secondary"
                    }
                  >
                    {person.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  {person.user ? (
                    <Badge
                      variant={
                        person.user.is_active ? "default" : "destructive"
                      }
                    >
                      {person.user.is_active ? "active" : "deactivated"}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="tabular-nums text-sm text-muted-foreground">
                  {stamp(person.user?.last_login_at)}
                </TableCell>
                <TableCell className="text-end">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant={
                        person.status === "active" ? "outline" : "default"
                      }
                      disabled={busy === person.user_id}
                      onClick={() =>
                        void suspend(
                          person,
                          person.status === "active" ? "suspended" : "active",
                        )
                      }
                    >
                      {person.status === "active" ? "Suspend" : "Reinstate"}
                    </Button>
                    {person.user ? (
                      <Button
                        variant={
                          person.user.is_active ? "destructive" : "default"
                        }
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
