"use client";

import { useCallback, useEffect, useState } from "react";
import { Route as RouteIcon, Truck, UserRound } from "lucide-react";
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
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader, StatTile } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

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
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<RunGeneration | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, v, d, runList] = await Promise.all([
        listRoutes(),
        listVehicles(),
        listDrivers(),
        listDeliveryRuns(),
      ]);
      setRoutes(r);
      setVehicles(v);
      setDrivers(d);
      setRuns(runList);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "could not load routes");
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
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        description="Which customers a round visits, in what order, and who took it out today."
        title="Routes and runs"
      />

      <section
        aria-label="Route summary"
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <StatTile
          icon={<RouteIcon className="size-4" />}
          label="Routes"
          value={routes.length}
        />
        <StatTile icon={<Truck className="size-4" />} label="Vehicles" value={vehicles.length} />
        <StatTile
          icon={<UserRound className="size-4" />}
          label="Drivers"
          value={drivers.length}
        />
        <StatTile label="Runs today" value={runs.length} />
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
          {generated.slot}: {generated.created} of {generated.stops} stops generated
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
        onAssign={(id, body) => act(() => assignDeliveryRun(id, body))}
        onCreate={(routeId) => act(() => createDeliveryRun({ route_id: routeId }))}
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
            { key: "code", label: "Code", placeholder: "R-01" },
            { key: "name", label: "Name", placeholder: "Kilima morning round" },
          ]}
          icon={RouteIcon}
          onSubmit={(v) => act(() => createRoute({ code: v.code, name: v.name }))}
          title="Add a route"
        />
        <RegisterCard
          description="A vehicle this dairy uses, in either direction."
          fields={[
            { key: "registration", label: "Registration", placeholder: "KDA 123X" },
            { key: "label", label: "Label", placeholder: "Blue van" },
          ]}
          icon={Truck}
          onSubmit={(v) =>
            act(() => createVehicle({ registration: v.registration, label: v.label }))
          }
          title="Add a vehicle"
        />
        <RegisterCard
          description="A driver need not have a platform login."
          fields={[
            { key: "code", label: "Code", placeholder: "DRV-1" },
            { key: "full_name", label: "Name", placeholder: "Joseph Mwangi" },
          ]}
          icon={UserRound}
          onSubmit={(v) => act(() => createDriver({ code: v.code, full_name: v.full_name }))}
          title="Add a driver"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Routes</CardTitle>
          <CardDescription>
            A route is retired rather than deleted, because yesterday&apos;s runs still
            point at it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {routes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No routes yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 pr-4 font-medium">Code</th>
                  <th className="py-1 pr-4 font-medium">Name</th>
                  <th className="py-1 pr-4 font-medium">Stops</th>
                  <th className="py-1 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {routes.map((route) => (
                  <tr className="border-t border-border" key={route.id}>
                    <td className="py-2 pr-4 font-mono text-xs">{route.code}</td>
                    <td className="py-2 pr-4">{route.name}</td>
                    <td className="py-2 pr-4">{route.stop_count}</td>
                    <td className="py-2">
                      <StatusBadge status={route.active ? "active" : "inactive"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TodaysRuns({
  routes,
  runs,
  vehicles,
  drivers,
  onCreate,
  onGenerate,
  onAssign,
  onStatus,
}: {
  routes: Route[];
  runs: DeliveryRun[];
  vehicles: Vehicle[];
  drivers: Driver[];
  onCreate: (routeId: string) => void;
  onGenerate: (id: string) => void;
  onAssign: (id: string, body: { vehicle_id?: string; driver_id?: string }) => void;
  onStatus: (id: string, status: string) => void;
}) {
  const [routeId, setRouteId] = useState("");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Today&apos;s runs</CardTitle>
        <CardDescription>
          The dairy&apos;s today, not this browser&apos;s — the date is resolved from the
          organization&apos;s timezone.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="run-route">Route</Label>
            <select
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
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
            </select>
          </div>
          <Button disabled={!routeId} onClick={() => onCreate(routeId)} size="sm">
            Plan today&apos;s run
          </Button>
        </div>

        {runs.length === 0 ? (
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
                    disabled={run.status === "completed" || run.status === "cancelled"}
                    label="Vehicle"
                    onChange={(id) => onAssign(run.id, { vehicle_id: id })}
                    options={vehicles
                      .filter((v) => v.active)
                      .map((v) => ({ id: v.id, label: v.registration }))}
                    value={run.vehicle_id}
                  />
                  <Assign
                    disabled={run.status === "completed" || run.status === "cancelled"}
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
      <select
        className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
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
      </select>
    </div>
  );
}

function RegisterCard({
  title,
  description,
  icon: Icon,
  fields,
  onSubmit,
}: {
  title: string;
  description: string;
  icon: React.ElementType;
  fields: { key: string; label: string; placeholder: string }[];
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
