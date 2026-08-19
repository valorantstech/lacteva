"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, PenLine } from "lucide-react";
import {
  ApiError,
  type Center,
  type MilkTransaction,
  type ReadinessResult,
  type Supplier,
  acceptTransaction,
  captureMilk,
  captureQuality,
  captureWeight,
  completeTransaction,
  createMilkTransaction,
  getMilkTransaction,
  getReadiness,
  identifySupplier,
  listCenters,
  listCollectionSessions,
  listSuppliers,
  openCollectionSession,
} from "@/lib/api";
import { Stamp } from "@/components/datetime";
import { EntityPicker } from "@/components/entity-picker";
import { todayIn } from "@/components/date-range";
import { useLocale, useT } from "@/lib/i18n";
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
import { Money, Quantity } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { cn } from "@/lib/utils";

/**
 * Guided collection capture (DEMO-005).
 *
 * THE BACKEND IS THE STATE MACHINE. This wizard has no state machine of its
 * own: the step it shows is DERIVED from `transaction.state`, which the
 * platform sets. Every button is one real call to one real endpoint, and the
 * answer that comes back decides what happens next. A front-end state machine
 * would be a second source of truth, and the two would eventually disagree in
 * front of a customer.
 *
 * The real states, in order:
 *
 *   NEW → SUPPLIER_IDENTIFIED → MILK_RECEIVED → WEIGHT_CAPTURED
 *       → QUALITY_PENDING (the platform hands off automatically)
 *       → QUALITY_CAPTURED → PRICING_PENDING → PRICED
 *       → ACCEPTED | REJECTED → COMPLETED
 *
 * Because the step is derived, a browser refresh is safe: the id is kept in
 * `sessionStorage`, the transaction is re-read, and the wizard resumes exactly
 * where the PLATFORM says it is — not where the browser last thought it was.
 *
 * Measurements are entered by hand and sent with `source: "manual"`, which is
 * the domain's own name for an operator reading. The mock scale and mock
 * analyzer are refused outright in this environment, and nothing here pretends
 * a device supplied a value.
 */

const STORAGE_KEY = "lacteva.collection.in-progress";

/** Plausibility bounds mirrored from the domain, for a fast message only. */
const LIMITS = {
  maxGross: 200,
  fat: [0, 15],
  snf: [0, 15],
  clr: [20, 40],
} as const;

const MILK_TYPES = ["cow", "buffalo", "goat", "mixed"] as const;

type StepKey =
  "centre" | "supplier" | "milk" | "weight" | "quality" | "review" | "done";

const STEPS: { key: StepKey; labelKey: string }[] = [
  { key: "centre", labelKey: "tx.centre" },
  { key: "supplier", labelKey: "entity.supplier" },
  { key: "milk", labelKey: "txDetail.milk" },
  { key: "weight", labelKey: "transaction.weight" },
  { key: "quality", labelKey: "transaction.quality" },
  { key: "review", labelKey: "wizard.reviewAccept" },
  { key: "done", labelKey: "wizard.complete" },
];

/** The platform's state, translated into which step the operator is on. */
function stepFor(tx: MilkTransaction | null): StepKey {
  if (!tx) return "centre";
  switch (tx.state) {
    case "NEW":
      return "supplier";
    case "SUPPLIER_IDENTIFIED":
      return "milk";
    case "MILK_RECEIVED":
      return "weight";
    case "WEIGHT_CAPTURED":
    case "QUALITY_PENDING":
      return "quality";
    case "QUALITY_CAPTURED":
    case "PRICING_PENDING":
    case "PRICED":
    case "ACCEPTED":
    case "REJECTED":
      return "review";
    case "COMPLETED":
    case "CANCELLED":
      return "done";
    default:
      return "review";
  }
}

const reason = (e: unknown, fallback: string) =>
  e instanceof ApiError
    ? // The platform's `extra` carries the business reason; `detail` is the
      // generic RFC-9457 sentence. Prefer the specific one.
      (e.extra as string) || e.detail
    : e instanceof Error
      ? e.message
      : fallback;

export default function NewCollectionPage() {
  const [centers, setCenters] = useState<Center[]>([]);
  // P1-PORTAL-SCALE-001: no prefetched supplier list — the audit's dairy with
  // 500 farmers could not pick farmer #101 from a 100-row <select>. The
  // picker searches the platform; this holds whichever supplier was picked
  // (or resolved from an in-flight transaction), and this alone.
  const [pickedSupplier, setPickedSupplier] = useState<Supplier | null>(null);
  const [pickedLabel, setPickedLabel] = useState("");
  const fetchedSuppliers = useRef<Record<string, Supplier>>({});
  const [centerId, setCenterId] = useState("");
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [checkingReadiness, setCheckingReadiness] = useState(false);

  const [tx, setTx] = useState<MilkTransaction | null>(null);
  const { timezone: orgTimezone, t } = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resuming, setResuming] = useState(true);

  const [supplierId, setSupplierId] = useState("");
  const [milk, setMilk] = useState({
    milk_type: "cow",
    container_type: "can",
    container_identifier: "",
  });
  const [weight, setWeight] = useState({ gross: "", tare: "" });
  const [quality, setQuality] = useState({ fat: "", snf: "", clr: "" });
  const [fieldError, setFieldError] = useState<Record<string, string>>({});

  const step = stepFor(tx);

  // --- resume ---------------------------------------------------------------
  // Deferred rather than run in the effect body: a synchronous setState there
  // cascades a render, and `sessionStorage` is unavailable during SSR anyway.
  useEffect(() => {
    const timer = setTimeout(() => {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (!stored) {
        setResuming(false);
        return;
      }
      // The PLATFORM decides where we are. A stored id is only a pointer.
      getMilkTransaction(stored)
        .then((found) => {
          if (["COMPLETED", "CANCELLED"].includes(found.state)) {
            sessionStorage.removeItem(STORAGE_KEY);
          } else {
            setTx(found);
            setCenterId(found.center_id);
          }
        })
        .catch(() => sessionStorage.removeItem(STORAGE_KEY))
        .finally(() => setResuming(false));
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    listCenters({ limit: 100, offset: 0 })
      .then((c) => setCenters(c.items ?? []))
      .catch(() => setCenters([]));
  }, []);

  // Resuming an in-flight transaction: resolve its supplier by id so the
  // review and done steps can show a name rather than a UUID fragment.
  useEffect(() => {
    const id = tx?.supplier_id;
    if (!id || pickedSupplier?.id === id) return;
    listSuppliers({ ids: [id], limit: 1, offset: 0 })
      .then((p) => {
        const found = (p.items ?? [])[0];
        if (found) {
          setPickedSupplier(found);
          setPickedLabel(`${found.full_name} (${found.code})`);
        }
      })
      .catch(() => {
        // The honest fallback (truncated id) keeps rendering.
      });
  }, [tx?.supplier_id, pickedSupplier?.id]);

  useEffect(() => {
    if (!centerId || tx) return;
    const timer = setTimeout(() => {
      setCheckingReadiness(true);
      setReadiness(null);
      getReadiness(centerId)
        .then(setReadiness)
        .catch(() => setReadiness(null))
        .finally(() => setCheckingReadiness(false));
    }, 0);
    return () => clearTimeout(timer);
  }, [centerId, tx]);

  /** Run one real backend step; keep whatever the platform says came back. */
  const run = useCallback(
    async (action: () => Promise<MilkTransaction>) => {
      setBusy(true);
      setError(null);
      try {
        const next = await action();
        setTx(next);
        sessionStorage.setItem(STORAGE_KEY, next.id);
        if (["COMPLETED", "CANCELLED"].includes(next.state)) {
          sessionStorage.removeItem(STORAGE_KEY);
        }
        return true;
      } catch (e) {
        setError(reason(e, t("wizard.platformRefused")));
        // Re-read: a refusal may mean the platform moved on without us
        // (a duplicate submit, another operator), and guessing would be worse
        // than asking.
        if (tx) {
          try {
            setTx(await getMilkTransaction(tx.id));
          } catch {
            /* keep what we have */
          }
        }
        return false;
      } finally {
        setBusy(false);
      }
    },
    [tx, t],
  );

  const startCollection = async () => {
    setBusy(true);
    setError(null);
    try {
      // Join the centre's open session if there is one; a centre permits only
      // one, and taking someone else's shift is not this screen's business.
      const open = await listCollectionSessions({
        center_id: centerId,
        status: "open",
      });
      const session =
        open.items?.[0] ??
        // The DAIRY's date. A session opened at 00:30 in Nairobi belongs to
        // that day's collection, and a UTC label named it after yesterday.
        (await openCollectionSession(
          centerId,
          `Guided capture ${todayIn(orgTimezone)}`,
        ));
      const created = await createMilkTransaction(session.id);
      setTx(created);
      sessionStorage.setItem(STORAGE_KEY, created.id);
    } catch (e) {
      setError(reason(e, t("wizard.platformRefused")));
    } finally {
      setBusy(false);
    }
  };

  const abandon = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    setTx(null);
    setError(null);
    setSupplierId("");
    setWeight({ gross: "", tare: "" });
    setQuality({ fat: "", snf: "", clr: "" });
  };

  const centre = centers.find((c) => c.id === (tx?.center_id ?? centerId));
  const wantedSupplierId = tx?.supplier_id ?? supplierId;
  const supplier =
    pickedSupplier && pickedSupplier.id === wantedSupplierId
      ? pickedSupplier
      : undefined;
  const ready =
    readiness?.status === "READY" || readiness?.status === "WARNING";

  if (resuming) {
    return (
      <div className="p-8">
        <LoadingState label={t("wizard.checkingInProgress")} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        breadcrumbs={[
          { label: "Collections", href: "/transactions" },
          { label: "New collection" },
        ]}
        title="Record a collection"
        description="Each step is a real operation on the platform. The platform decides what comes next."
        actions={
          tx ? (
            <Button
              type="button"
              variant="ghost"
              onClick={abandon}
              disabled={busy}
            >
              Start over
            </Button>
          ) : undefined
        }
      />

      <Stepper current={step} />

      {tx ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
          <span className="text-muted-foreground">Collection</span>
          <span className="font-mono text-xs">{tx.id}</span>
          <StatusBadge status={tx.state} />
          <span className="ml-auto text-xs text-muted-foreground">
            started {String(tx.created_at).slice(11, 16)}
          </span>
        </div>
      ) : null}

      {error ? (
        // The platform's own business reason, not a generic apology.
        <ErrorState message={error} />
      ) : null}

      {step === "centre" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">1 · Collection centre</CardTitle>
            <CardDescription>
              Milk can only be received at a centre the platform considers
              ready.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="w-center">Centre</Label>
              <select
                id="w-center"
                className="h-9 w-full max-w-md rounded-md border border-input bg-background px-2 text-sm"
                value={centerId}
                onChange={(e) => setCenterId(e.target.value)}
              >
                <option value="">Select a centre…</option>
                {centers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.code}) — {c.status}
                  </option>
                ))}
              </select>
            </div>

            {checkingReadiness ? (
              <LoadingState label="Checking readiness…" />
            ) : null}

            {readiness ? (
              <div className="rounded-lg border border-border p-3">
                <div className="mb-2 flex items-center gap-2">
                  <StatusBadge status={readiness.status} />
                  <span className="text-xs text-muted-foreground">
                    {centre?.timezone ?? ""}
                  </span>
                </div>
                <ul className="flex flex-col gap-1.5 text-sm">
                  {(readiness.checks ?? []).map((check) => (
                    <li key={check.rule} className="flex items-start gap-2">
                      {check.passed ? (
                        <Check
                          aria-hidden
                          className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
                        />
                      ) : (
                        <AlertTriangle
                          aria-hidden
                          className={cn(
                            "mt-0.5 size-3.5 shrink-0",
                            check.severity === "blocking"
                              ? "text-destructive"
                              : "text-muted-foreground",
                          )}
                        />
                      )}
                      <span
                        className={check.passed ? "text-muted-foreground" : ""}
                      >
                        {check.rule.replace(/[_.]/g, " ")}
                        {!check.passed && check.detail ? (
                          <span className="block text-xs text-muted-foreground">
                            {check.detail}
                          </span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
                {!ready ? (
                  <p role="alert" className="mt-3 text-sm text-destructive">
                    This centre cannot receive milk until the blocking checks
                    above pass.
                  </p>
                ) : null}
              </div>
            ) : null}

            <div>
              <Button
                type="button"
                disabled={!centerId || !ready || busy}
                onClick={() => void startCollection()}
              >
                {busy ? "Starting…" : "Start collection"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "supplier" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">2 · Supplier</CardTitle>
            <CardDescription>
              Only an active supplier may deliver. The platform refuses the
              rest.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <EntityPicker
              id="w-supplier"
              label="Supplier"
              placeholder="Search by name, code or phone…"
              className="w-full max-w-md"
              value={supplierId}
              valueLabel={pickedLabel || undefined}
              onSelect={(id, label) => {
                setSupplierId(id);
                setPickedLabel(label);
                setPickedSupplier(fetchedSuppliers.current[id] ?? null);
              }}
              search={async (q, offset) => {
                const page = await listSuppliers({
                  q: q || undefined,
                  status: "active",
                  limit: 20,
                  offset,
                });
                for (const s of page.items ?? []) {
                  fetchedSuppliers.current[s.id] = s;
                }
                return {
                  items: (page.items ?? []).map((s) => ({
                    id: s.id,
                    label: `${s.full_name} (${s.code})`,
                    detail: s.phone || undefined,
                  })),
                  total: page.total,
                };
              }}
            />
            <div>
              <Button
                type="button"
                disabled={!supplierId || busy}
                onClick={() =>
                  void run(() => identifySupplier(tx!.id, supplierId))
                }
              >
                {busy ? "Identifying…" : "Identify supplier"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "milk" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">3 · Milk and container</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="w-milk">Milk type</Label>
                <select
                  id="w-milk"
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  value={milk.milk_type}
                  onChange={(e) =>
                    setMilk({ ...milk, milk_type: e.target.value })
                  }
                >
                  {MILK_TYPES.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="w-container">Container</Label>
                <select
                  id="w-container"
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  value={milk.container_type}
                  onChange={(e) =>
                    setMilk({ ...milk, container_type: e.target.value })
                  }
                >
                  {["can", "drum", "tanker"].map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="w-container-id">Container ID</Label>
                <Input
                  id="w-container-id"
                  value={milk.container_identifier}
                  placeholder="CAN-01"
                  onChange={(e) =>
                    setMilk({ ...milk, container_identifier: e.target.value })
                  }
                  aria-invalid={Boolean(fieldError.container)}
                />
                {fieldError.container ? (
                  <p role="alert" className="text-xs text-destructive">
                    {fieldError.container}
                  </p>
                ) : null}
              </div>
            </div>
            <div>
              <Button
                type="button"
                disabled={busy}
                onClick={() => {
                  if (!milk.container_identifier.trim()) {
                    setFieldError({
                      container: "Give the container an identifier.",
                    });
                    return;
                  }
                  setFieldError({});
                  void run(() =>
                    captureMilk(tx!.id, {
                      ...milk,
                      container_identifier: milk.container_identifier.trim(),
                    }),
                  );
                }}
              >
                {busy ? "Recording…" : "Record milk"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "weight" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">4 · Weight</CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              <PenLine aria-hidden className="size-3.5" />
              Manual demo capture — entered by an operator, not read from a
              scale.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="w-gross">Gross weight (kg)</Label>
                <Input
                  id="w-gross"
                  inputMode="decimal"
                  value={weight.gross}
                  placeholder="12.000"
                  onChange={(e) =>
                    setWeight({ ...weight, gross: e.target.value })
                  }
                  aria-invalid={Boolean(fieldError.gross)}
                />
                {fieldError.gross ? (
                  <p role="alert" className="text-xs text-destructive">
                    {fieldError.gross}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Up to {LIMITS.maxGross} kg.
                  </p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="w-tare">Tare weight (kg)</Label>
                <Input
                  id="w-tare"
                  inputMode="decimal"
                  value={weight.tare}
                  placeholder="2.000"
                  onChange={(e) =>
                    setWeight({ ...weight, tare: e.target.value })
                  }
                  aria-invalid={Boolean(fieldError.tare)}
                />
                {fieldError.tare ? (
                  <p role="alert" className="text-xs text-destructive">
                    {fieldError.tare}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    The empty container.
                  </p>
                )}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Net weight is computed by the platform, not here.
            </p>
            <div>
              <Button
                type="button"
                disabled={busy}
                onClick={() => {
                  const errors: Record<string, string> = {};
                  const gross = Number(weight.gross);
                  const tare = Number(weight.tare);
                  if (!weight.gross || !Number.isFinite(gross) || gross <= 0)
                    errors.gross = "Enter a gross weight greater than zero.";
                  else if (gross > LIMITS.maxGross)
                    errors.gross = `The platform accepts at most ${LIMITS.maxGross} kg.`;
                  if (!weight.tare || !Number.isFinite(tare) || tare < 0)
                    errors.tare = "Enter a tare weight of zero or more.";
                  else if (Number.isFinite(gross) && tare >= gross)
                    errors.tare = "Tare must be less than gross.";
                  setFieldError(errors);
                  if (Object.keys(errors).length) return;
                  void run(() => captureWeight(tx!.id, { gross, tare }));
                }}
              >
                {busy ? "Recording…" : "Record weight"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "quality" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">5 · Quality</CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              <PenLine aria-hidden className="size-3.5" />
              Manual demo capture. Fat decides which rate band applies.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-3">
              {(
                [
                  ["fat", "Fat %", LIMITS.fat, "4.2"],
                  ["snf", "SNF", LIMITS.snf, "8.6"],
                  ["clr", "CLR", LIMITS.clr, "28.5"],
                ] as const
              ).map(([key, label, range, placeholder]) => (
                <div key={key} className="flex flex-col gap-1.5">
                  <Label htmlFor={`w-${key}`}>{label}</Label>
                  <Input
                    id={`w-${key}`}
                    inputMode="decimal"
                    value={quality[key]}
                    placeholder={placeholder}
                    onChange={(e) =>
                      setQuality({ ...quality, [key]: e.target.value })
                    }
                    aria-invalid={Boolean(fieldError[key])}
                  />
                  {fieldError[key] ? (
                    <p role="alert" className="text-xs text-destructive">
                      {fieldError[key]}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {range[0]}–{range[1]}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Recording quality asks the pricing engine for a rate. The next
              screen shows what it returned.
            </p>
            <div>
              <Button
                type="button"
                disabled={busy}
                onClick={() => {
                  const errors: Record<string, string> = {};
                  for (const [key, range] of [
                    ["fat", LIMITS.fat],
                    ["snf", LIMITS.snf],
                    ["clr", LIMITS.clr],
                  ] as const) {
                    const value = Number(quality[key]);
                    if (!quality[key] || !Number.isFinite(value))
                      errors[key] = "Enter a reading.";
                    else if (value < range[0] || value > range[1])
                      errors[key] =
                        `The platform accepts ${range[0]}–${range[1]}.`;
                  }
                  setFieldError(errors);
                  if (Object.keys(errors).length) return;
                  void run(() =>
                    captureQuality(tx!.id, {
                      fat: Number(quality.fat),
                      snf: Number(quality.snf),
                      clr: Number(quality.clr),
                    }),
                  );
                }}
              >
                {busy ? "Pricing…" : "Record quality and price"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === "review" && tx ? (
        <ReviewStep
          tx={tx}
          centre={centre}
          supplier={supplier}
          busy={busy}
          onAccept={() => void run(() => acceptTransaction(tx.id))}
          onComplete={() => void run(() => completeTransaction(tx.id))}
        />
      ) : null}

      {step === "done" && tx ? (
        <DoneStep tx={tx} centre={centre} supplier={supplier} />
      ) : null}
    </div>
  );
}

function Stepper({ current }: { current: StepKey }) {
  const t = useT();
  const index = STEPS.findIndex((s) => s.key === current);
  return (
    <ol className="flex flex-wrap gap-2" aria-label={t("wizard.progress")}>
      {STEPS.map((s, i) => {
        const state =
          i < index ? "completed" : i === index ? "current" : "pending";
        return (
          <li
            key={s.key}
            aria-current={state === "current" ? "step" : undefined}
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs",
              state === "completed" && "border-border text-muted-foreground",
              state === "current" && "border-primary bg-primary/5 font-medium",
              state === "pending" &&
                "border-dashed border-border text-muted-foreground",
            )}
          >
            {state === "completed" ? (
              <Check aria-hidden className="size-3" />
            ) : null}
            {t(s.labelKey)}
            <span className="sr-only"> — {state}</span>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Review, accept, complete.
 *
 * The pricing figures are the platform's: `unit_price` and `gross_amount` were
 * written by the pricing engine when quality was captured. This screen prints
 * them; it does not multiply anything.
 */
function ReviewStep({
  tx,
  centre,
  supplier,
  busy,
  onAccept,
  onComplete,
}: {
  tx: MilkTransaction;
  centre?: Center;
  supplier?: Supplier;
  busy: boolean;
  onAccept: () => void;
  onComplete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const priced = tx.unit_price != null && tx.gross_amount != null;
  const accepted = tx.state === "ACCEPTED";
  const rejected = tx.state === "REJECTED";

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">6 · Review</CardTitle>
          <CardDescription>
            Everything below came back from the platform.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <dl className="flex flex-col gap-2.5 text-sm">
            <Row label="Supplier">
              {supplier?.full_name ?? tx.supplier_id?.slice(0, 8) ?? "—"}
            </Row>
            <Row label="Centre">{centre?.name ?? tx.center_id.slice(0, 8)}</Row>
            <Row label="Milk">{tx.milk_type ?? "—"}</Row>
            <Row label="Quantity">
              <Quantity value={tx.net_weight} unit={tx.weight_unit ?? "kg"} />
            </Row>
            <Row label="Fat">{tx.fat ?? "—"}%</Row>
            <Row label="SNF">{tx.snf ?? "—"}</Row>
            <Row label="CLR">{tx.clr ?? "—"}</Row>
          </dl>

          {!priced ? (
            <EmptyState
              title="Awaiting a price"
              description="The pricing engine has not answered yet."
            />
          ) : (
            <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Pricing
              </p>
              <dl className="flex flex-col gap-2 text-sm">
                <Row label="Rate card">
                  <span className="text-end text-muted-foreground">
                    {tx.pricing_detail ?? "—"}
                  </span>
                </Row>
                <Row label="Rate">
                  <span className="tabular-nums">
                    {String(tx.unit_price)}
                    <span className="ms-1 text-xs text-muted-foreground">
                      {tx.currency}/{tx.weight_unit ?? "kg"}
                    </span>
                  </span>
                </Row>
              </dl>
              {/* Printed, not evaluated — the operands and the result are three
                  values the platform sent. */}
              <div className="rounded-md bg-muted/40 p-2 font-mono text-sm tabular-nums">
                <div>
                  {String(tx.net_weight)} × {String(tx.unit_price)}
                </div>
                <div>
                  = {String(tx.gross_amount)} {tx.currency}
                </div>
              </div>
              <div className="flex items-baseline justify-between border-t border-border pt-2">
                <span className="text-sm text-muted-foreground">
                  Collection value
                </span>
                <Money
                  amount={tx.gross_amount}
                  currency={tx.currency}
                  emphasis
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">7 · Accept and complete</CardTitle>
          <CardDescription>
            Acceptance and completion are separate decisions, as they are in the
            domain.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {rejected ? (
            <p role="status" className="text-sm">
              This collection was rejected
              {tx.rejected_reason ? `: ${tx.rejected_reason}` : ""}. It still
              needs completing to close the paperwork.
            </p>
          ) : null}

          {!accepted && !rejected ? (
            confirming ? (
              <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
                <p className="text-sm">
                  Accept this collection at{" "}
                  <strong>
                    <Money amount={tx.gross_amount} currency={tx.currency} />
                  </strong>
                  ? The amount becomes payable to the supplier.
                </p>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    disabled={busy || !priced}
                    onClick={onAccept}
                  >
                    {busy ? "Accepting…" : "Yes, accept"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setConfirming(false)}
                    disabled={busy}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <Button
                  type="button"
                  disabled={busy || !priced}
                  onClick={() => setConfirming(true)}
                >
                  Accept collection
                </Button>
              </div>
            )
          ) : null}

          {accepted || rejected ? (
            <div>
              <Button type="button" disabled={busy} onClick={onComplete}>
                {busy ? "Completing…" : "Complete collection"}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function DoneStep({
  tx,
  centre,
  supplier,
}: {
  tx: MilkTransaction;
  centre?: Center;
  supplier?: Supplier;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Check aria-hidden className="size-4 text-primary" />
          Collection {tx.state.toLowerCase()}
        </CardTitle>
        <CardDescription>
          The collection is recorded. What follows is separate business.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <dl className="grid gap-2.5 text-sm sm:grid-cols-2">
          <Row label="Collection">
            <span className="font-mono text-xs">{tx.id}</span>
          </Row>
          <Row label="Status">
            <StatusBadge status={tx.state} />
          </Row>
          <Row label="Supplier">
            {supplier?.full_name ?? tx.supplier_id?.slice(0, 8) ?? "—"}
          </Row>
          <Row label="Centre">{centre?.name ?? tx.center_id.slice(0, 8)}</Row>
          <Row label="Quantity">
            <Quantity value={tx.net_weight} unit={tx.weight_unit ?? "kg"} />
          </Row>
          <Row label="Rate">
            <span className="tabular-nums">{String(tx.unit_price ?? "—")}</span>
          </Row>
          <Row label="Value">
            <Money amount={tx.gross_amount} currency={tx.currency} emphasis />
          </Row>
          <Row label="Completed">
            <Stamp value={tx.completed_at ?? tx.created_at} />
          </Row>
        </dl>

        {/* Completion is NOT payment. Saying so plainly is the point. */}
        <div className="rounded-lg border border-dashed border-border p-4">
          <p className="mb-2 text-sm font-medium">Still to happen</p>
          <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
            <li>
              ○ Settlement — this collection becomes payable when a settlement
              period collects it
            </li>
            <li>○ Payment — raised against a finalized settlement</li>
            <li>○ Receipt — generated once the payment completes</li>
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Collection completion is not settlement, and settlement is not
            payment. Each is a separate business stage.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            href={`/transactions/${tx.id}`}
            className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            Open this collection
          </Link>
          <Link
            href="/transactions/new"
            className="inline-flex h-9 items-center rounded-md border border-input px-4 text-sm hover:bg-muted"
            onClick={() => sessionStorage.removeItem(STORAGE_KEY)}
          >
            Record another
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-end">{children}</dd>
    </div>
  );
}
