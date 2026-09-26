"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Route as RouteIcon, Truck, UserRound, X } from "lucide-react";
import {
  ApiError,
  type DeliveryRun,
  type Driver,
  type Route,
  type RunGeneration,
  type Vehicle,
  assignDeliveryRun,
  createDeliveryRun,
  createDriver,
  createRoute,
  createVehicle,
  generateDeliveryRun,
  listDeliveryRuns,
  listDrivers,
  listRoutes,
  listVehicles,
  setDeliveryRunStatus,
  updateRoute,
  getRoute,
  setRouteStops,
  listCustomers,
  listMembers,
  linkDriverUser,
  type Member,
  type RouteStop,
  type Customer,
  getUser,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/page-header";
import { PageContainer } from "@/components/page-container";
import { LoadingState } from "@/components/states";
import { Skeleton } from "@/components/skeleton";
import { Metric, Surface } from "@/components/surface";
import { StatusBadge } from "@/components/status-badge";
import { type Column, DataTable } from "@/components/data-table";
import { roleLabel } from "@/lib/roles";

/**
 * Routes, fleet and today's rounds (DEMO-034).
 *
 * The physical layer under a delivery round: which customers are visited and
 * in what order, who took the round out and in what.
 *
 * **Nothing on this page is a financial figure**, and that is the design
 * rather than an omission. What a household was delivered and what it is worth
 * belongs to the deliveries screen, which is the only place that knows it. A
 * stop here shows the delivery domain's own status — or a dash, when there is
 * no delivery row yet, which truthfully reads as "not visited".
 */

/** What the operator may do next, given where the run is. */
const NEXT_ACTIONS: Record<string, { status: string; label: string }[]> = {
  planned: [
    { status: "in_progress", label: "Start" },
    { status: "cancelled", label: "Cancel" },
  ],
  in_progress: [
    { status: "completed", label: "Complete" },
    { status: "cancelled", label: "Cancel" },
  ],
  completed: [],
  cancelled: [],
};

export default function RoutesPage() {
  const [routes, setRoutes] = useState<Route[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [runs, setRuns] = useState<DeliveryRun[]>([]);
  // WO-108: the organisation's people, for "which login is this delivery
  // boy?" — and which round's stops are being edited.
  const [members, setMembers] = useState<Member[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [editingStops, setEditingStops] = useState<Route | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<RunGeneration | null>(null);
  // LACTEVA-ADMIN-001: every list here starts `[]`, so on first paint the
  // summary read a confident "0" routes, "0" vehicles, "0" drivers and "0"
  // runs — four figures the page had not yet asked for. A count nobody has
  // established is worse than no count.
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [r, v, d, runList, people] = await Promise.all([
        listRoutes(),
        listVehicles(),
        listDrivers(),
        listDeliveryRuns(),
        // Not every reader may list members; the link select is then simply
        // absent rather than the whole page failing.
        listMembers().catch(() => [] as Member[]),
      ]);
      setRoutes(r);
      setVehicles(v);
      setDrivers(d);
      setRuns(runList);
      setMembers(people);
      // The members list carries roles, not names; the few people holding
      // the Delivery boy role are named from their user records.
      const boys = people.filter((m) => (m.roles ?? []).some((r) => r.name === "DRIVER"));
      const users = await Promise.all(boys.map((m) => getUser(m.user_id).catch(() => null)));
      setNames(
        Object.fromEntries(
          users.filter(Boolean).map((u) => [u!.id, u!.full_name || u!.email]),
        ),
      );
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "could not load routes");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setError(null);
      await load();
    } catch (e) {
      // The platform's refusals are the interesting ones — "a run needs both a
      // driver and a vehicle before it can start" is the message an operator
      // has to act on, so it is shown verbatim rather than replaced.
      setError(e instanceof ApiError ? e.message : "the change was refused");
    }
  };

  return (
    <PageContainer width="wide">
      <PageHeader
        description="Which customers a round visits, in what order, and who took it out today."
        title="Routes and runs"
      />

      <section
        aria-label="Route summary"
        className="grid grid-cols-2 gap-4 xl:grid-cols-4"
      >
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Routes"
            value={loading ? <Skeleton className="h-9 w-10" /> : routes.length}
          />
          <span aria-hidden className="text-muted-foreground">
            <RouteIcon className="size-4" />
          </span>
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Vehicles"
            value={
              loading ? <Skeleton className="h-9 w-10" /> : vehicles.length
            }
          />
          <span aria-hidden className="text-muted-foreground">
            <Truck className="size-4" />
          </span>
        </Surface>
        <Surface
          tone="metric"
          className="flex items-start justify-between gap-3"
        >
          <Metric
            label="Drivers"
            value={loading ? <Skeleton className="h-9 w-10" /> : drivers.length}
          />
          <span aria-hidden className="text-muted-foreground">
            <UserRound className="size-4" />
          </span>
        </Surface>
        <Surface tone="metric">
          <Metric
            label="Runs today"
            value={loading ? <Skeleton className="h-9 w-10" /> : runs.length}
          />
        </Surface>
      </section>

      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {generated && (
        <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
          {/* `created: 0` is idempotency holding, not a failure — so the
              sentence says which it is rather than leaving a bare zero. */}
          <strong>{generated.route_code}</strong> · {generated.business_date} ·{" "}
          {generated.slot}: {generated.created} of {generated.stops} stops
          generated
          {generated.already_present > 0 &&
            `, ${generated.already_present} already there`}
          {generated.not_due > 0 && `, ${generated.not_due} not due today`}
          {generated.inactive_customers > 0 &&
            `, ${generated.inactive_customers} inactive`}
          .
        </p>
      )}

      <TodaysRuns
        drivers={drivers}
        loading={loading}
        onAssign={(id, body) => act(() => assignDeliveryRun(id, body))}
        onCreate={(routeId) =>
          act(() => createDeliveryRun({ route_id: routeId }))
        }
        onGenerate={(id) =>
          act(async () => setGenerated(await generateDeliveryRun(id)))
        }
        onStatus={(id, status) => act(() => setDeliveryRunStatus(id, status))}
        routes={routes}
        runs={runs}
        vehicles={vehicles}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <RegisterCard
          description="A named round. Its stops are set on the round itself."
          fields={[
            { key: "name", label: "Name", placeholder: "Morning round" },
          ]}
          optional={[
            {
              key: "code",
              label: "Code (optional — generated from the name)",
              placeholder: "MORNING-ROUND",
            },
          ]}
          icon={RouteIcon}
          onSubmit={(v) =>
            act(() =>
              createRoute({
                name: v.name,
                ...(v.code?.trim() ? { code: v.code.trim() } : {}),
              }),
            )
          }
          title="Add a route"
        />
        <RegisterCard
          description="A vehicle this dairy uses, in either direction."
          fields={[
            {
              key: "registration",
              label: "Registration",
              placeholder: "KDA 123X",
            },
            { key: "label", label: "Label", placeholder: "Blue van" },
          ]}
          icon={Truck}
          onSubmit={(v) =>
            act(() =>
              createVehicle({ registration: v.registration, label: v.label }),
            )
          }
          title="Add a vehicle"
        />
        <RegisterCard
          description="A driver need not have a platform login."
          fields={[
            { key: "full_name", label: "Name", placeholder: "Ramesh Pawar" },
          ]}
          optional={[
            {
              key: "code",
              label: "Code (optional — generated from the name)",
              placeholder: "RAMESH-PAWAR",
            },
          ]}
          icon={UserRound}
          onSubmit={(v) =>
            act(() =>
              createDriver({
                full_name: v.full_name,
                ...(v.code?.trim() ? { code: v.code.trim() } : {}),
              }),
            )
          }
          title="Add a driver"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Routes</CardTitle>
          <CardDescription>
            A route is retired rather than deleted, because yesterday&apos;s
            runs still point at it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && routes.length === 0 ? (
            <LoadingState label="Loading routes…" />
          ) : routes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No routes yet.</p>
          ) : (
            <DataTable
              caption="Routes"
              rowKey={(route) => route.id}
              rows={routes}
              columns={routeColumns({
                drivers,
                vehicles,
                act,
                editing: editingStops?.id ?? null,
                onEditStops: (route) =>
                  setEditingStops((current) => (current?.id === route.id ? null : route)),
              })}
            />
          )}
          <p className="pt-3 text-xs text-muted-foreground">
            With a default driver and &ldquo;auto-plan&rdquo; on, the round will
            exist every morning without anyone creating it: the platform creates
            the day&apos;s run at its generation hour, assigns the driver (and the
            vehicle, if named) and generates the deliveries. A non-working day is
            skipped.
          </p>
        </CardContent>
      </Card>

      {editingStops ? (
        <RouteStopsEditor
          key={editingStops.id}
          route={editingStops}
          onClose={() => setEditingStops(null)}
          onSaved={() => {
            setEditingStops(null);
            void load();
          }}
        />
      ) : null}

      <DeliveryBoys drivers={drivers} members={members} names={names} act={act} />
    </PageContainer>
  );
}

function TodaysRuns({
  routes,
  runs,
  vehicles,
  drivers,
  loading,
  onCreate,
  onGenerate,
  onAssign,
  onStatus,
}: {
  routes: Route[];
  runs: DeliveryRun[];
  vehicles: Vehicle[];
  drivers: Driver[];
  /** The page's first fetch is still in flight (LACTEVA-ADMIN-001). */
  loading: boolean;
  onCreate: (routeId: string) => void;
  onGenerate: (id: string) => void;
  onAssign: (
    id: string,
    body: { vehicle_id?: string; driver_id?: string },
  ) => void;
  onStatus: (id: string, status: string) => void;
}) {
  const [routeId, setRouteId] = useState("");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Today&apos;s runs</CardTitle>
        <CardDescription>
          The dairy&apos;s today, not this browser&apos;s — the date is resolved
          from the organization&apos;s timezone.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="run-route">Route</Label>
            <Select
              id="run-route"
              onChange={(e) => setRouteId(e.target.value)}
              value={routeId}
            >
              <option value="">Choose a route…</option>
              {routes
                .filter((r) => r.active)
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.code} — {r.name}
                  </option>
                ))}
            </Select>
          </div>
          <Button
            disabled={!routeId}
            onClick={() => onCreate(routeId)}
            size="sm"
          >
            Plan today&apos;s run
          </Button>
        </div>

        {loading && runs.length === 0 ? (
          <LoadingState label="Loading today's runs…" />
        ) : runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No run planned for today yet.
          </p>
        ) : (
          <div className="space-y-4">
            {runs.map((run) => (
              <div className="rounded-md border border-border p-3" key={run.id}>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-medium">
                    {run.route_code} — {run.route_name}
                  </span>
                  <StatusBadge status={run.status} />
                  <span className="text-xs text-muted-foreground">
                    {run.business_date} · {run.slot}
                  </span>
                  {/* Generating into a closed round would add work to a day
                      somebody has signed off, so the platform refuses it and
                      the button is not offered either. */}
                  {run.status !== "completed" && run.status !== "cancelled" && (
                    <Button
                      onClick={() => onGenerate(run.id)}
                      size="sm"
                      variant="outline"
                    >
                      Generate round
                    </Button>
                  )}
                  {NEXT_ACTIONS[run.status]?.map((action) => (
                    <Button
                      key={action.status}
                      onClick={() => onStatus(run.id, action.status)}
                      size="sm"
                      variant="outline"
                    >
                      {action.label}
                    </Button>
                  ))}
                </div>

                <div className="mt-2 flex flex-wrap items-end gap-3 text-sm">
                  <Assign
                    disabled={
                      run.status === "completed" || run.status === "cancelled"
                    }
                    label="Vehicle"
                    onChange={(id) => onAssign(run.id, { vehicle_id: id })}
                    options={vehicles
                      .filter((v) => v.active)
                      .map((v) => ({ id: v.id, label: v.registration }))}
                    value={run.vehicle_id}
                  />
                  <Assign
                    disabled={
                      run.status === "completed" || run.status === "cancelled"
                    }
                    label="Driver"
                    onChange={(id) => onAssign(run.id, { driver_id: id })}
                    options={drivers
                      .filter((d) => d.active)
                      .map((d) => ({ id: d.id, label: d.full_name }))}
                    value={run.driver_id}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Assign({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: string | null;
  options: { id: string; label: string }[];
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={`assign-${label}`}>{label}</Label>
      <Select
        disabled={disabled}
        id={`assign-${label}`}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        value={value ?? ""}
      >
        <option value="">Unassigned</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </Select>
    </div>
  );
}

function RegisterCard({
  title,
  description,
  icon: Icon,
  fields,
  optional = [],
  onSubmit,
}: {
  title: string;
  description: string;
  icon: React.ElementType;
  fields: { key: string; label: string; placeholder: string }[];
  /** WO-107 §3: fields nobody has to fill — the code, generated from the
   *  name when left blank — folded under "More options". */
  optional?: { key: string; label: string; placeholder: string }[];
  onSubmit: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const complete = fields.every((f) => (values[f.key] ?? "").trim().length > 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon aria-hidden className="size-4" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {fields.map((field) => (
          <div className="grid gap-1.5" key={field.key}>
            <Label htmlFor={`${title}-${field.key}`}>{field.label}</Label>
            <Input
              id={`${title}-${field.key}`}
              onChange={(e) =>
                setValues((v) => ({ ...v, [field.key]: e.target.value }))
              }
              placeholder={field.placeholder}
              value={values[field.key] ?? ""}
            />
          </div>
        ))}
        {optional.length > 0 ? (
          <details>
            <summary className="cursor-pointer text-xs text-muted-foreground">
              More options
            </summary>
            <div className="mt-2 space-y-3">
              {optional.map((field) => (
                <div className="grid gap-1.5" key={field.key}>
                  <Label htmlFor={`${title}-${field.key}`}>{field.label}</Label>
                  <Input
                    id={`${title}-${field.key}`}
                    onChange={(e) =>
                      setValues((v) => ({ ...v, [field.key]: e.target.value }))
                    }
                    placeholder={field.placeholder}
                    value={values[field.key] ?? ""}
                  />
                </div>
              ))}
            </div>
          </details>
        ) : null}
        <Button
          disabled={!complete}
          onClick={() => {
            onSubmit(values);
            setValues({});
          }}
          size="sm"
        >
          Add
        </Button>
      </CardContent>
    </Card>
  );
}


/**
 * WO-108 §2: the round's stops — which customers, in delivery order — edited
 * on a phone: search a customer and add them, move a stop up or down with a
 * button (no drag needed at 360px), remove one, save. The list IS the order
 * the platform stores.
 */
function RouteStopsEditor({
  route,
  onClose,
  onSaved,
}: {
  route: Route;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [stops, setStops] = useState<RouteStop[] | null>(null);
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Customer[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRoute(route.id)
      .then((detail) => !cancelled && setStops(detail.stops))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "could not load the stops"));
    return () => {
      cancelled = true;
    };
  }, [route.id]);

  useEffect(() => {
    let cancelled = false;
    // Debounced, and the short-query clear happens on the same tick as a
    // search would — never a state write straight from the effect body.
    const t = setTimeout(() => {
      if (q.trim().length < 2) {
        setFound([]);
        return;
      }
      listCustomers({ q: q.trim(), status: "active", limit: 8, offset: 0 })
        .then((page) => !cancelled && setFound(page.items))
        .catch(() => !cancelled && setFound([]));
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [q]);

  function move(index: number, delta: number) {
    setStops((current) => {
      if (!current) return current;
      const next = [...current];
      const target = index + delta;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((s, i) => ({ ...s, position: i + 1 }));
    });
  }

  const current = stops ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Stops of {route.name}</CardTitle>
        <CardDescription>
          In delivery order, top to bottom. Add a customer by name, move a stop
          with the arrows, and save.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {stops === null && !error ? <LoadingState label="Loading stops…" /> : null}
        <ol className="flex flex-col divide-y" aria-label="Stops">
          {current.map((stop, index) => (
            <li key={stop.customer_id} className="flex items-center gap-2 py-2">
              <span className="w-6 shrink-0 text-xs text-muted-foreground">{index + 1}.</span>
              <span className="min-w-0 flex-1 truncate text-sm">
                {stop.name}
                <span className="ms-1 text-xs text-muted-foreground">{stop.code}</span>
              </span>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Move ${stop.name} up`}
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                <ArrowUp className="size-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Move ${stop.name} down`}
                disabled={index === current.length - 1}
                onClick={() => move(index, 1)}
              >
                <ArrowDown className="size-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Remove ${stop.name}`}
                onClick={() => setStops(current.filter((s) => s.customer_id !== stop.customer_id))}
              >
                <X className="size-4" />
              </Button>
            </li>
          ))}
        </ol>
        {stops !== null && current.length === 0 ? (
          <p className="text-sm text-muted-foreground">No stops yet — add the first customer below.</p>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`stops-search-${route.id}`}>Add a customer</Label>
          <Input
            id={`stops-search-${route.id}`}
            placeholder="Type a name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {found.length > 0 ? (
            <ul className="flex flex-col divide-y rounded-md border border-border" aria-label="Matching customers">
              {found
                .filter((c) => !current.some((s) => s.customer_id === c.id))
                .map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-3 py-2 text-start text-sm hover:bg-muted"
                      onClick={() => {
                        setStops([
                          ...current,
                          { customer_id: c.id, position: current.length + 1, code: c.code, name: c.name },
                        ]);
                        setQ("");
                      }}
                    >
                      <span className="truncate">{c.name}</span>
                      <span className="ms-2 shrink-0 text-xs text-muted-foreground">add</span>
                    </button>
                  </li>
                ))}
            </ul>
          ) : null}
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            disabled={saving || stops === null}
            onClick={async () => {
              setSaving(true);
              setError(null);
              try {
                await setRouteStops(route.id, current.map((s) => s.customer_id));
                onSaved();
              } catch (e) {
                setError(e instanceof ApiError ? e.message : "could not save the stops");
              } finally {
                setSaving(false);
              }
            }}
          >
            {saving ? "Saving…" : "Save stops"}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * WO-108 §2: the delivery boys, and which login each one is. A boy invited as
 * a Delivery boy arrives here already linked (the platform makes his profile
 * when he accepts). A profile made by hand — before this work order, or for
 * a name that already existed — is linked from the select: the members
 * holding the Delivery boy role who are not yet on a profile.
 */
function DeliveryBoys({
  drivers,
  members,
  names,
  act,
}: {
  drivers: Driver[];
  members: Member[];
  /** user_id → the person's name, for the members holding the role. */
  names: Record<string, string>;
  act: (fn: () => Promise<unknown>) => void;
}) {
  const boys = members.filter((m) => (m.roles ?? []).some((r) => r.name === "DRIVER"));
  const linkedUsers = new Set(drivers.map((d) => d.user_id).filter(Boolean));
  const name = (m: Member) => names[m.user_id] ?? m.user_id;
  if (drivers.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Delivery boys</CardTitle>
        <CardDescription>
          Invite a delivery boy from Staff and his profile appears here linked to
          his login. A profile made by hand is linked to a login below.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y" aria-label="Delivery boys">
          {drivers
            .filter((d) => d.active)
            .map((driver) => {
              const holder = members.find((m) => m.user_id === driver.user_id);
              return (
                <li key={driver.id} className="flex flex-wrap items-center gap-2 py-2">
                  <span className="min-w-0 flex-1 text-sm">
                    {driver.full_name}
                    <span className="ms-1 font-mono text-xs text-muted-foreground">{driver.code}</span>
                  </span>
                  {driver.user_id ? (
                    <span className="text-xs text-muted-foreground">
                      {roleLabel("DRIVER")} login: {holder ? name(holder) : "linked"}
                    </span>
                  ) : (
                    <Select
                      aria-label={`Login for ${driver.full_name}`}
                      value=""
                      onChange={(e) => {
                        if (e.target.value) act(() => linkDriverUser(driver.id, e.target.value));
                      }}
                    >
                      <option value="">— no app login yet —</option>
                      {boys
                        .filter((m) => !linkedUsers.has(m.user_id))
                        .map((m) => (
                          <option key={m.user_id} value={m.user_id}>
                            {name(m)}
                          </option>
                        ))}
                    </Select>
                  )}
                </li>
              );
            })}
        </ul>
      </CardContent>
    </Card>
  );
}

/**
 * The route list as columns (WO-96 §1), so the phone shows each round as a
 * card with its driver, vehicle and the every-morning switch beneath the
 * name rather than off the right edge.
 */
function routeColumns({
  drivers,
  vehicles,
  act,
  editing,
  onEditStops,
}: {
  drivers: Driver[];
  vehicles: Vehicle[];
  act: (fn: () => Promise<unknown>) => void;
  /** WO-108 §2: the route whose stops are open in the editor below. */
  editing: string | null;
  onEditStops: (route: Route) => void;
}): Column<Route>[] {
  // WO-108 §2: the default delivery boy is chosen from the LINKED drivers —
  // a profile with a login is one whose phone will show the round.
  const linked = drivers.filter((d) => d.active && d.user_id);
  return [
    { key: "code", header: "Code", role: "title", cell: (route) => <span className="font-mono text-xs">{route.code}</span> },
    { key: "name", header: "Name", role: "subtitle", cell: (route) => route.name },
    {
      key: "stops",
      header: "Stops",
      cell: (route) => (
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-label={`Edit the stops of ${route.name}`}
          aria-pressed={editing === route.id}
          onClick={() => onEditStops(route)}
        >
          {route.stop_count} {route.stop_count === 1 ? "stop" : "stops"} · edit
        </Button>
      ),
    },
    { key: "status", header: "Status", role: "status", cell: (route) => <StatusBadge status={route.active ? "active" : "inactive"} /> },
    // WO-82 §3: the round will exist every morning without anyone creating
    // it — when a default driver is named and the switch is on.
    {
      key: "driver",
      header: "Delivery boy",
      cell: (route) => (
        <Select
          aria-label={`Default delivery boy for ${route.code}`}
          value={route.default_driver_id ?? ""}
          onChange={(e) =>
            act(() =>
              updateRoute(
                route.id,
                e.target.value ? { default_driver_id: e.target.value } : { clear_default_driver: true },
              ),
            )
          }
        >
          <option value="">— none —</option>
          {linked.map((d) => (
            <option key={d.id} value={d.id}>
              {d.full_name}
            </option>
          ))}
          {/* A default set before this work order, on a profile without a
              login, stays visible rather than silently vanishing. */}
          {route.default_driver_id && !linked.some((d) => d.id === route.default_driver_id)
            ? drivers
                .filter((d) => d.id === route.default_driver_id)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.full_name} (no app login)
                  </option>
                ))
            : null}
        </Select>
      ),
    },
    {
      key: "transport",
      header: "Goes out by",
      cell: (route) => (
        <Select
          aria-label={`How ${route.code} goes out`}
          value={route.transport ?? "vehicle"}
          onChange={(e) =>
            act(() =>
              updateRoute(route.id, {
                transport: e.target.value as "vehicle" | "on_foot" | "bicycle",
              }),
            )
          }
        >
          <option value="vehicle">vehicle</option>
          <option value="on_foot">on foot</option>
          <option value="bicycle">bicycle</option>
        </Select>
      ),
    },
    {
      key: "vehicle",
      header: "Default vehicle",
      cell: (route) => (
        <Select
          aria-label={`Default vehicle for ${route.code}`}
          value={route.default_vehicle_id ?? ""}
          onChange={(e) =>
            act(() =>
              updateRoute(
                route.id,
                e.target.value ? { default_vehicle_id: e.target.value } : { clear_default_vehicle: true },
              ),
            )
          }
        >
          <option value="">— none —</option>
          {vehicles.map((v) => (
            <option key={v.id} value={v.id}>
              {v.registration}
            </option>
          ))}
        </Select>
      ),
    },
    {
      key: "auto",
      header: "Every morning",
      cell: (route) => (
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            aria-label={`Plan ${route.code} every morning`}
            checked={route.auto_plan === true}
            disabled={!route.default_driver_id}
            onChange={(e) => act(() => updateRoute(route.id, { auto_plan: e.target.checked }))}
          />
          {route.default_driver_id ? "auto-plan" : "needs a default driver"}
        </label>
      ),
    },
  ];
}
