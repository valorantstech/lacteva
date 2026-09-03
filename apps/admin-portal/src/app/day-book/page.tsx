"use client";

/**
 * The milk day book (WO-56 · LACTEVA-STOCK-001 · BR-0030).
 *
 * What happened to the milk at a centre today: what came in, what went out in
 * bulk, and what that leaves. The dairy this platform is built for keeps this
 * on paper, and the paper is the thing a manager actually reconciles against
 * the tanker's gate pass — so this page is deliberately a ledger and not a
 * dashboard.
 *
 * Two honesty rules run through it, both of them the platform's rather than
 * this file's:
 *
 * **It is a FLOW ledger.** Collected minus dispatched. It cannot see
 * evaporation, spillage, a testing sample or milk carried over from
 * yesterday, and the page says so in a sentence rather than implying
 * precision it does not have. A negative remainder is shown as it falls out:
 * it means something was recorded wrong, and clamping it would hide exactly
 * that.
 *
 * **Sales sit beside the arithmetic, not inside it.** A delivery on this
 * platform has no centre and no milk type, and is a DIFFERENT POPULATION from
 * intake — lost, retained, dispatched, sold from stock held over — whatever
 * unit either side reads (WO-71). Subtracting it from a centre's remainder would look precise
 * and be wrong twice over, so the figure is shown with the reason it is not
 * subtracted. The flags come from the API; this page does not decide them.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale } from "@/lib/i18n";
import { BookOpen, Download, Droplets, TruckIcon } from "lucide-react";

import {
  ApiError,
  type Center,
  type DayBook,
  type Dispatch,
  cancelDispatch,
  dayBookCsvUrl,
  describeError,
  getDayBook,
  getSession,
  listCenters,
  listDispatches,
  recordDispatch,
  type Session,
  can,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useBusinessToday } from "@/components/date-range";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Metric, Surface } from "@/components/surface";
import { PageContainer } from "@/components/page-container";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { formatQuantity } from "@/components/money";
import { unitLabel } from "@/lib/units";
import { isCompleteDate } from "@/lib/complete-date";

/** The platform's own vocabulary (`core/milk.py`). `custom` is included: a
 *  dairy that recorded milk as custom can dispatch it as custom. */
const MILK_TYPES = ["cow", "buffalo", "goat", "sheep", "mixed", "custom"] as const;

const LABEL: Record<string, string> = {
  cow: "Cow",
  buffalo: "Buffalo",
  goat: "Goat",
  sheep: "Sheep",
  mixed: "Mixed",
  custom: "Other",
};

/** A figure in the BOOK'S unit (D-21) — read from the ledger, never assumed. */
const qty = (n: number, unit: string) => `${formatQuantity(n)} ${unitLabel(unit)}`;

export default function DayBookPage() {
  const { quantityUnit } = useLocale();
  const businessToday = useBusinessToday();
  const [session, setSession] = useState<Session | null>(null);
  const [centers, setCenters] = useState<Center[]>([]);
  const [centerId, setCenterId] = useState("");
  /**
   * What is in the date box — including whatever a half-typed date is.
   *
   * WO-73: DERIVED from the dairy's today until the reader picks a day, not
   * copied into state at mount. The shell mounts pages before the session
   * probe answers, so on the first render the timezone is null and
   * `businessToday` is UTC-today; a `useState(businessToday)` kept that
   * forever, and at 03:20 IST this page opened on yesterday — the window a
   * dairy's morning shift starts in. `useDefaultRange` already solves this
   * shape for the dashboard; it is a range with presets, and the day book
   * is one date, so the same two-lifetimes rule is applied here directly
   * rather than through a range the page would immediately flatten.
   */
  const [chosenDay, setChosenDay] = useState<string | null>(null);
  const day = chosenDay ?? businessToday;
  /**
   * The date the ledger is SHOWING (WO-68). A `<input type="date">` emits
   * intermediate values while someone types — `0008-30-2026` was captured
   * from a real browser — and sending one to the platform earned a 422 that
   * killed the page. Typing into a date field is normal, not misuse: the
   * ledger holds the last complete date until the next complete one arrives,
   * and nothing incomplete is ever sent.
   */
  const [chosenShownDay, setChosenShownDay] = useState<string | null>(null);
  const shownDay = chosenShownDay ?? businessToday;
  const changeDay = (value: string) => {
    setChosenDay(value);
    if (isCompleteDate(value)) setChosenShownDay(value);
  };
  const [book, setBook] = useState<DayBook | null>(null);
  const [dispatches, setDispatches] = useState<Dispatch[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** The dispatch whose cancellation is being explained, and the words so far.
   *  A reason is mandatory (BR-0030), so it is asked for in the page rather
   *  than in a browser dialog nobody can style, translate or test. */
  const [cancelling, setCancelling] = useState<{ id: string; reason: string } | null>(null);

  const canRecord = can(session, "operations.dispatch.record");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextBook, page] = await Promise.all([
        getDayBook({ business_date: shownDay, center_id: centerId || undefined }),
        listDispatches({
          center_id: centerId || undefined,
          date_from: shownDay,
          date_to: shownDay,
        }),
      ]);
      setBook(nextBook);
      setDispatches(page.items);
    } catch (err) {
      setError(describeError(err, "Could not load the day book."));
    } finally {
      setLoading(false);
    }
  }, [centerId, shownDay]);

  useEffect(() => {
    void getSession().then(setSession);
    listCenters({ limit: 100, offset: 0 })
      .then((page) => setCenters(page.items))
      // A centre list that failed to load leaves the filter empty; the ledger
      // itself is unaffected, and reporting a second error over it would be
      // noise about a control rather than about the figures.
      .catch(() => setCenters([]));
  }, []);

  useEffect(() => {
    const t = setTimeout(() => void load(), 100);
    return () => clearTimeout(t);
  }, [load]);

  const centreName = useMemo(
    () => centers.find((c) => c.id === centerId)?.name ?? null,
    [centerId, centers],
  );

  const record = async (form: HTMLFormElement) => {
    const data = new FormData(form);
    setBusy(true);
    setFormError(null);
    try {
      await recordDispatch({
        center_id: String(data.get("center_id") ?? ""),
        business_date: shownDay,
        milk_type: String(data.get("milk_type") ?? "cow"),
        quantity: String(data.get("quantity") ?? ""),
        destination: String(data.get("destination") ?? ""),
        reference: String(data.get("reference") ?? ""),
      });
      form.reset();
      await load();
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? describeError(err)
          : "Could not record the dispatch.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer width="wide">
      <PageHeader
        breadcrumbs={[{ label: "Dashboard", href: "/" }, { label: "Day book" }]}
        title="Milk day book"
        description="What came in, what went out in bulk, and what that leaves — for one centre, on one day."
        actions={
          <a
            href={dayBookCsvUrl({
              business_date: shownDay,
              center_id: centerId || undefined,
            })}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-accent"
          >
            <Download className="size-4" />
            Download CSV
          </a>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="day-book-date">Business date</Label>
          <Input
            id="day-book-date"
            type="date"
            value={day}
            onChange={(e) => changeDay(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="day-book-centre">Centre</Label>
          <Select
            id="day-book-centre"
            value={centerId}
            onChange={(e) => setCenterId(e.target.value)}
          >
            <option value="">All centres</option>
            {centers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </div>
        <Button type="button" variant="outline" disabled={loading} onClick={() => void load()}>
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {error ? (
        <ErrorState
          message={error}
          action={
            <Button size="sm" variant="outline" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      ) : null}

      <section aria-label="Day totals" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric
            label="Collected"
            value={book ? qty(book.total_collected_kg, book.quantity_unit) : "—"}
            caption={centreName ?? "every centre"}
          />
          <span aria-hidden className="text-muted-foreground">
            <Droplets className="size-4" />
          </span>
        </Surface>
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric
            label="Dispatched"
            value={book ? qty(book.total_dispatched_kg, book.quantity_unit) : "—"}
            caption="sent out in bulk"
          />
          <span aria-hidden className="text-muted-foreground">
            <TruckIcon className="size-4" />
          </span>
        </Surface>
        <Surface tone="metric" className="flex items-start justify-between gap-3">
          <Metric
            label="Remainder"
            value={book ? qty(book.total_remainder_kg, book.quantity_unit) : "—"}
            caption="collected minus dispatched"
          />
          <span aria-hidden className="text-muted-foreground">
            <BookOpen className="size-4" />
          </span>
        </Surface>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">By milk type</CardTitle>
          <CardDescription>
            A flow ledger of recorded movements — not a measurement of a tank.
            It cannot see evaporation, spillage, testing samples or milk carried
            over from yesterday.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && !book ? (
            <LoadingState label="Loading the day book…" />
          ) : error ? (
            // List honesty: a ledger that failed to load is not a day with no
            // milk, and the empty state below must never stand in for one.
            <ErrorState
              message="Could not load the day book — this is not the same as a day with nothing in it."
              action={
                <Button size="sm" variant="outline" onClick={() => void load()}>
                  Try again
                </Button>
              }
            />
          ) : !book || book.rows.length === 0 ? (
            <EmptyState
              title="Nothing recorded for this day"
              description="No accepted collection and no dispatch at this centre on this date. That is not the same as a day with no milk — a day nobody recorded looks exactly like this one."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2 pe-3 font-medium">Milk type</th>
                    <th className="py-2 pe-3 text-end font-medium">Collected</th>
                    <th className="py-2 pe-3 text-end font-medium">Dispatched</th>
                    <th className="py-2 text-end font-medium">Remainder</th>
                  </tr>
                </thead>
                <tbody>
                  {book.rows.map((row) => (
                    <tr key={row.milk_type} className="border-b last:border-0">
                      <td className="py-2 pe-3">
                        {LABEL[row.milk_type] ?? row.milk_type}
                        <span className="ms-2 text-xs text-muted-foreground">
                          {row.collections} in · {row.dispatches} out
                        </span>
                      </td>
                      <td className="py-2 pe-3 text-end tabular-nums">
                        {qty(row.collected_kg, book.quantity_unit)}
                      </td>
                      <td className="py-2 pe-3 text-end tabular-nums">
                        {qty(row.dispatched_kg, book.quantity_unit)}
                      </td>
                      <td
                        className={`py-2 text-end font-medium tabular-nums ${
                          row.remainder_kg < 0 ? "text-destructive" : ""
                        }`}
                      >
                        {qty(row.remainder_kg, book.quantity_unit)}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td className="py-2 pe-3 font-medium">Total</td>
                    <td className="py-2 pe-3 text-end font-medium tabular-nums">
                      {qty(book.total_collected_kg, book.quantity_unit)}
                    </td>
                    <td className="py-2 pe-3 text-end font-medium tabular-nums">
                      {qty(book.total_dispatched_kg, book.quantity_unit)}
                    </td>
                    <td className="py-2 text-end font-medium tabular-nums">
                      {qty(book.total_remainder_kg, book.quantity_unit)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {book ? (
            <p className="mt-4 text-xs text-muted-foreground">
              Sold today: {formatQuantity(book.sales.quantity)} {book.sales.quantity_unit} across{" "}
              {book.sales.deliveries}{" "}
              {book.sales.deliveries === 1 ? "delivery" : "deliveries"}.{" "}
              {book.sales.attributable_to_centre
                ? null
                : "Sales are organization-wide and are not attributed to a centre"}
              {book.sales.attributable_to_milk_type ? null : " or to a milk type"}, and they are
              a different population from intake — milk is lost, retained, dispatched and sold
              from stock held over — so they are NOT subtracted from the remainder above.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dispatches</CardTitle>
          <CardDescription>
            Milk that left in bulk on this date. A dispatch cannot be edited: a
            wrong one is cancelled, with a reason, and the right one recorded —
            so a day book somebody has already read never changes shape behind
            them.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/*
            Absent, not disabled, for anyone without `operations.dispatch.record`
            — the same rule the wizard's rate control follows. A greyed-out
            button tells the reader the capability exists and they are not
            trusted with it.
          */}
          {canRecord ? (
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                void record(e.currentTarget);
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dispatch-centre">Centre</Label>
                <Select id="dispatch-centre" name="center_id" defaultValue={centerId} required>
                  <option value="">Choose a centre</option>
                  {centers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dispatch-type">Milk type</Label>
                <Select id="dispatch-type" name="milk_type" defaultValue="cow">
                  {MILK_TYPES.map((m) => (
                    <option key={m} value={m}>
                      {LABEL[m]}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dispatch-quantity">
                  Quantity ({book ? unitLabel(book.quantity_unit) : (quantityUnit ?? "…")})
                </Label>
                <Input
                  id="dispatch-quantity"
                  name="quantity"
                  inputMode="decimal"
                  placeholder="0.000"
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dispatch-destination">Destination</Label>
                <Input
                  id="dispatch-destination"
                  name="destination"
                  placeholder="Chilling plant, buyer, vehicle"
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="dispatch-reference">Reference</Label>
                <Input id="dispatch-reference" name="reference" placeholder="Gate pass / challan" />
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? "Recording…" : "Record dispatch"}
              </Button>
            </form>
          ) : null}

          {formError ? <ErrorState message={formError} /> : null}

          {dispatches === null && loading ? (
            <LoadingState label="Loading dispatches…" />
          ) : error || dispatches === null ? (
            <ErrorState message="Could not load the dispatches for this date — this is not the same as none having been recorded." />
          ) : dispatches.length === 0 ? (
            <EmptyState
              title="No dispatch recorded"
              description="Nothing left this centre in bulk on this date, as far as the platform was told."
            />
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {dispatches.map((d) => (
                <li
                  key={d.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {String(d.quantity)} {d.quantity_unit} ·{" "}
                      {LABEL[d.milk_type] ?? d.milk_type} → {d.destination}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {d.reference ? `${d.reference} · ` : ""}
                      {d.status === "cancelled"
                        ? `cancelled — ${d.cancel_reason}`
                        : d.business_date}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={d.status} />
                    {canRecord && d.status === "recorded" ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          setCancelling(
                            cancelling?.id === d.id ? null : { id: d.id, reason: "" },
                          )
                        }
                      >
                        Cancel
                      </Button>
                    ) : null}
                  </div>
                  {cancelling?.id === d.id ? (
                    <form
                      className="flex w-full flex-wrap items-end gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        setBusy(true);
                        setFormError(null);
                        void cancelDispatch(d.id, cancelling.reason)
                          .then(() => {
                            setCancelling(null);
                            return load();
                          })
                          .catch((err) =>
                            setFormError(
                              describeError(err, "Could not cancel the dispatch."),
                            ),
                          )
                          .finally(() => setBusy(false));
                      }}
                    >
                      <div className="flex grow flex-col gap-1.5">
                        <Label htmlFor={`cancel-reason-${d.id}`}>
                          Why is this dispatch being cancelled?
                        </Label>
                        <Input
                          id={`cancel-reason-${d.id}`}
                          value={cancelling.reason}
                          required
                          minLength={3}
                          placeholder="It stays in the record, with your reason"
                          onChange={(e) =>
                            setCancelling({ id: d.id, reason: e.target.value })
                          }
                        />
                      </div>
                      <Button type="submit" size="sm" disabled={busy}>
                        {busy ? "Cancelling…" : "Confirm cancellation"}
                      </Button>
                    </form>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
