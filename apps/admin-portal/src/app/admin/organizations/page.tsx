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
  type CountryChoice,
  type Me,
  type Organization,
  ORGANIZATION_TYPES,
  createOrganization,
  getMe,
  getOrganization,
  listCountries,
  proposeSlug,
  setActingTenant,
  describeError,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { UNITS, unitLabel } from "@/lib/units";

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
        describeError(err, "Failed to load the organization"),
      );
    }
  }, []);

  useEffect(() => {
    // Deferred, like every other page here: calling setState straight from an
    // effect body cascades a render.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  // Design System V1 (batch F): the quiet-label treatment `DataTable` gives
  // its column headers, applied here because this page uses the raw `Table`
  // primitive. Kept page-local for the same reason as the /admin/users pilot —
  // `DataTable` already styles its own heads, so pushing this into `TableHead`
  // would double the treatment everywhere else.
  return (
    <AdminPage
      title="Organization"
      description="The tenant this session acts inside, and the permissions it carries."
      error={error}
    >
      {me === null ? (
        <p>Loading…</p>
      ) : me.tenant_id === null ? (
        <div className="flex flex-col gap-6">
          <p className="text-sm text-muted-foreground">
            This is a platform-level session with no organization bound. Sign in
            with an organization id, or send <code>X-Tenant-ID</code>, to act
            inside a tenant.
          </p>
          {me.permissions.includes("*") ||
          me.permissions.includes("organization.manage") ? (
            <NewOrganizationForm />
          ) : null}
        </div>
      ) : (
        <Table>
          <TableBody>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Name
              </TableHead>
              <TableCell>{org?.name ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Slug
              </TableHead>
              <TableCell>{org?.slug ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Country
              </TableHead>
              <TableCell>{org?.country_code?.toUpperCase() ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Tenant id
              </TableHead>
              <TableCell className="font-mono text-xs">
                {me.tenant_id}
              </TableCell>
            </TableRow>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Signed in as
              </TableHead>
              <TableCell>{me.user.email}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead className="text-meta font-semibold uppercase tracking-wide text-muted-foreground">
                Permissions
              </TableHead>
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

/**
 * New organisation (WO-80). The playbook said this screen existed on
 * 2026-09-01; it did not, and provisioning was a raw API call. Platform
 * sessions only (`organization.manage`): name, a slug proposed from the name
 * and editable, country, organisation type, and the one unit question D-21
 * asks at creation. Everything else — currency, timezone, language — resolves
 * from the country, which is DEMO-013's whole point.
 *
 * On success the page offers "Act in this organisation" (the acting-tenant
 * cookie the chip reads) and the road to Admin → Users → Invite, because an
 * organisation with no administrator is not yet a customer.
 */
function NewOrganizationForm() {
  const [countries, setCountries] = useState<CountryChoice[]>([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [country, setCountry] = useState("");
  const [orgType, setOrgType] = useState<string>("cooperative");
  const [unit, setUnit] = useState<(typeof UNITS)[number]>("litre");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Organization | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCountries()
      .then((r) => {
        if (!cancelled) setCountries(r.countries);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const org = await createOrganization({
        name: name.trim(),
        slug: slug.trim(),
        country_code: country,
        org_type: orgType,
        quantity_unit: unit,
      });
      setCreated(org);
    } catch (err) {
      setError(describeError(err, "The organisation could not be created"));
    } finally {
      setBusy(false);
    }
  }

  async function actIn(org: Organization) {
    setBusy(true);
    setError(null);
    try {
      await setActingTenant(org.id);
      // A full navigation: the acting tenant lives in a cookie the shell reads
      // on load, and the first job in a new organisation is inviting its admin.
      window.location.assign("/admin/users");
    } catch (err) {
      setError(describeError(err, "Could not act in the organisation"));
      setBusy(false);
    }
  }

  if (created) {
    return (
      <section
        className="flex flex-col gap-3 rounded-md border border-border bg-card p-4 text-sm"
        data-testid="organization-created"
        role="status"
      >
        <h2 className="text-base font-semibold">
          {created.name} is created
        </h2>
        <p className="text-muted-foreground">
          Slug <code>{created.slug}</code> · id{" "}
          <code className="font-mono text-xs">{created.id}</code>. A 30-day trial
          starts now. Next: act in it and invite the dairy owner as{" "}
          <code>tenant-admin</code> under Admin → Users.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void actIn(created)}>
            Act in this organisation
          </Button>
          <a
            className="inline-flex h-9 items-center rounded-md border border-input px-3 text-sm hover:bg-muted"
            href="/admin/users"
          >
            Admin → Users → Invite
          </a>
        </div>
        {error ? (
          <p role="alert" className="text-destructive">
            The platform refused: {error}
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="flex max-w-xl flex-col gap-4 rounded-md border border-border bg-card p-4"
      aria-labelledby="new-organization-title"
      data-testid="new-organization"
    >
      <h2 id="new-organization-title" className="text-base font-semibold">
        New organisation
      </h2>
      <p className="text-xs text-muted-foreground">
        Currency, timezone and language follow the country; the unit is the one
        question asked here, and it can be changed later under Admin → Settings.
      </p>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="org-name">Name</Label>
        <Input
          id="org-name"
          required
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (!slugEdited) setSlug(proposeSlug(e.target.value));
          }}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="org-slug">Slug</Label>
        <Input
          id="org-slug"
          required
          pattern="[a-z0-9][a-z0-9-]{1,78}[a-z0-9]"
          value={slug}
          onChange={(e) => {
            setSlugEdited(true);
            setSlug(e.target.value);
          }}
        />
        <span className="text-xs text-muted-foreground">
          Proposed from the name; lower-case letters, digits and dashes.
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="org-country">Country</Label>
          <Select
            id="org-country"
            required
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          >
            <option value="">Choose…</option>
            {countries.map((c) => (
              <option key={c.code} value={c.code.toLowerCase()}>
                {c.name} ({c.currency_code})
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="org-type">Organisation type</Label>
          <Select id="org-type" value={orgType} onChange={(e) => setOrgType(e.target.value)}>
            {ORGANIZATION_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-sm font-medium">Milk is</legend>
        {UNITS.map((u) => (
          <label key={u} className="inline-flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="quantity_unit"
              value={u}
              checked={unit === u}
              onChange={() => setUnit(u)}
            />
            {u === "litre" ? "Measured in litres" : "Weighed in kilograms"}
            <span className="text-xs text-muted-foreground">({unitLabel(u)})</span>
          </label>
        ))}
      </fieldset>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          The platform refused: {error}
        </p>
      ) : null}
      <div>
        <Button type="submit" disabled={busy || !name.trim() || !slug.trim() || !country}>
          {busy ? "Creating…" : "Create organisation"}
        </Button>
      </div>
    </form>
  );
}
