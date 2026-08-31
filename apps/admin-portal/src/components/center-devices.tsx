"use client";

/**
 * The machines at a centre, manageable without curl (WO-53 · LACTEVA-ADMIN-018).
 *
 * The device registry has existed since P0-HW-001 — categories, lifecycle,
 * health, readiness semantics, permissions, RLS — and until now it had **zero
 * UI callers**. `listCenterDevices` sat in the portal's API module unreferenced
 * by any screen. A dairy could not register the scale that blocks its own
 * collection sessions without a shell and a bearer token, which means the
 * readiness rules the platform enforces were unreachable by the people they
 * govern.
 *
 * The semantics here are the platform's, not this card's: an active assigned
 * SCALE is a blocking readiness check, an analyzer and a printer are warnings,
 * and status moves registered → assigned → active → maintenance → retired.
 * Nothing is decided in the browser; every button is one existing endpoint.
 */

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  type Device,
  DEVICE_CATEGORIES,
  assignDevice,
  listCenterDevices,
  registerDevice,
  setDeviceStatus,
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
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";

/** How the platform reads each category, in the operator's words. */
const CATEGORY_LABEL: Record<string, string> = {
  scale: "Scale",
  milk_analyzer: "Milk analyzer",
  printer: "Printer",
  qr_scanner: "QR scanner",
};

/** Which categories stop a session, and which merely warn. */
const BLOCKING: ReadonlySet<string> = new Set(["scale"]);

type Load<T> =
  | { state: "loading" }
  | { state: "error"; error: unknown }
  | { state: "ready"; data: T };

export function CenterDevices({
  centerId,
  canManage,
}: {
  centerId: string;
  /** `operations.device.manage`. Read-only viewers see the list and no controls. */
  canManage: boolean;
}) {
  const [load, setLoad] = useState<Load<Device[]>>({ state: "loading" });
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const page = await listCenterDevices(centerId);
      setLoad({ state: "ready", data: page.items });
    } catch (e) {
      setLoad({ state: "error", error: e });
    }
  }, [centerId]);

  useEffect(() => {
    // Deferred, as every other loader in this tree is: a synchronous setState
    // inside an effect body cascades renders, and the lint rule says so.
    const t = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(t);
  }, [refresh]);

  const move = async (device: Device, status: string) => {
    setBusyId(device.id);
    setError(null);
    try {
      await setDeviceStatus(device.id, status);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not change the status.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Devices</CardTitle>
        <CardDescription>
          An active scale is required before a collection session can open. An
          analyzer and a printer are warnings, not blockers.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {load.state === "loading" ? (
          <LoadingState label="Loading devices…" />
        ) : load.state === "error" ? (
          <ErrorState
            // List honesty: an unreachable list is not an empty one, and a
            // centre whose devices failed to load must not read as a centre
            // with no devices.
            message="Could not load devices — this is not the same as the centre having none."
            action={
              <Button size="sm" variant="outline" onClick={() => void refresh()}>
                Try again
              </Button>
            }
          />
        ) : load.data.length === 0 ? (
          <EmptyState
            title="No devices registered"
            description="Collections can still be recorded by hand — a centre with no scale simply cannot open a session until one is registered and active."
          />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {load.data.map((device) => (
              <li
                key={device.id}
                className="flex flex-wrap items-center justify-between gap-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {device.name}
                    {BLOCKING.has(device.category) && (
                      <span className="ms-2 text-xs font-normal text-muted-foreground">
                        blocks sessions
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {CATEGORY_LABEL[device.category] ?? device.category}
                    {device.make || device.model
                      ? ` · ${[device.make, device.model].filter(Boolean).join(" ")}`
                      : ""}
                    {` · ${device.serial_number}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={device.status} />
                  {canManage && device.status !== "retired" && (
                    <>
                      {device.status === "registered" && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === device.id}
                          onClick={() => {
                            setBusyId(device.id);
                            void assignDevice(device.id, centerId)
                              .then(refresh)
                              .catch(() =>
                                setError("Could not assign the device."),
                              )
                              .finally(() => setBusyId(null));
                          }}
                        >
                          Assign here
                        </Button>
                      )}
                      {device.status === "assigned" && (
                        <Button
                          size="sm"
                          disabled={busyId === device.id}
                          onClick={() => void move(device, "active")}
                        >
                          Activate
                        </Button>
                      )}
                      {device.status === "active" && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === device.id}
                          onClick={() => void move(device, "maintenance")}
                        >
                          Maintenance
                        </Button>
                      )}
                      {device.status === "maintenance" && (
                        <Button
                          size="sm"
                          disabled={busyId === device.id}
                          onClick={() => void move(device, "active")}
                        >
                          Back in service
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busyId === device.id}
                        onClick={() => void move(device, "retired")}
                      >
                        Retire
                      </Button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {canManage &&
          (adding ? (
            <RegisterDeviceForm
              centerId={centerId}
              onDone={() => {
                setAdding(false);
                void refresh();
              }}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <Button variant="outline" onClick={() => setAdding(true)}>
              Register a device
            </Button>
          ))}
      </CardContent>
    </Card>
  );
}

function RegisterDeviceForm({
  centerId,
  onDone,
  onCancel,
}: {
  centerId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [category, setCategory] = useState<string>("scale");
  const [name, setName] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [serial, setSerial] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (name.trim().length < 2) errors.name = "Give the device a name.";
    if (serial.trim().length < 2)
      errors.serial =
        "A serial number is how a reading is traced back to a machine.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setBusy(true);
    setError(null);
    try {
      // Register, then assign, then leave it ASSIGNED — activating is a
      // separate, deliberate act, because an active scale changes whether the
      // centre may open a session at all.
      const device = await registerDevice({
        category,
        name: name.trim(),
        serial_number: serial.trim(),
        make: make.trim(),
        model: model.trim(),
      });
      await assignDevice(device.id, centerId);
      onDone();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not register the device. The serial number may already be in use.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-3 rounded-lg border border-border p-3"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="device-category">Category</Label>
          <Select
            id="device-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {DEVICE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c] ?? c}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="device-name">Name</Label>
          <Input
            id="device-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Intake bay scale"
          />
          {fieldErrors.name && (
            <p className="text-xs text-destructive">{fieldErrors.name}</p>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="device-make">Make</Label>
          <Input
            id="device-make"
            value={make}
            onChange={(e) => setMake(e.target.value)}
            placeholder="Optional"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="device-model">Model</Label>
          <Input
            id="device-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="Optional"
          />
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="device-serial">Serial number</Label>
          <Input
            id="device-serial"
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="From the label on the machine"
          />
          {fieldErrors.serial && (
            <p className="text-xs text-destructive">{fieldErrors.serial}</p>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Registering…" : "Register and assign"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
